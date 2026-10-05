"""Build source-backed geometry. Missing children never imply terminal cities."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from opencc import OpenCC
from shapely import coverage_is_valid, coverage_simplify, get_parts, make_valid, transform
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data" / "geo"
RAW = GEO / "raw" / "admin_2026"
LEVELS = ("province", "city", "district")
MUNICIPAL = {"110000", "120000", "310000", "500000"}
TERMINAL_PREFECTURES = {"441900": "东莞市", "442000": "中山市", "460400": "儋州市", "620200": "嘉峪关市"}
CC = OpenCC("t2s")
SOURCE_VERSION = "2025.251231.260403"


def dump(path, value, pretty=False):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2 if pretty else None,
                               separators=None if pretty else (",", ":")), encoding="utf-8")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def gcj_to_wgs(points):
    """Display-scale approximate inverse; identical shared vertices stay identical."""
    lon, lat = points[:, 0], points[:, 1]
    x, y = lon - 105, lat - 35
    dlat = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*np.sqrt(np.abs(x))
    dlat += (20*np.sin(6*x*np.pi) + 20*np.sin(2*x*np.pi))*2/3
    dlat += (20*np.sin(y*np.pi) + 40*np.sin(y/3*np.pi))*2/3
    dlat += (160*np.sin(y/12*np.pi) + 320*np.sin(y*np.pi/30))*2/3
    dlon = 300 + x + 2*y + .1*x*x + .1*x*y + .1*np.sqrt(np.abs(x))
    dlon += (20*np.sin(6*x*np.pi) + 20*np.sin(2*x*np.pi))*2/3
    dlon += (20*np.sin(x*np.pi) + 40*np.sin(x/3*np.pi))*2/3
    dlon += (150*np.sin(x/12*np.pi) + 300*np.sin(x/30*np.pi))*2/3
    rad = lat / 180*np.pi
    magic = 1 - .00669342162296594323 * np.sin(rad)**2
    dlat *= 180/((6378245*(1-.00669342162296594323))/(magic*np.sqrt(magic))*np.pi)
    dlon *= 180/(6378245/np.sqrt(magic)*np.cos(rad)*np.pi)
    mask = (lon >= 72.004) & (lon <= 137.8347) & (lat >= .8293) & (lat <= 55.8271)
    return np.column_stack((lon-np.where(mask,dlon,0), lat-np.where(mask,dlat,0)))


def polygon_only(geometry):
    if geometry.is_empty: return geometry
    if not geometry.is_valid: geometry = make_valid(geometry)
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        polygons = []
        for part in get_parts(geometry):
            if part.geom_type == "Polygon": polygons.append(part)
            elif part.geom_type == "MultiPolygon": polygons.extend(part.geoms)
        geometry = MultiPolygon(polygons)
    return geometry


def parse_polygon(value):
    if not value or value == "EMPTY": return None
    polygons = []
    for block in value.split(";"):
        rings = []
        for ring in block.split("~"):
            points = [tuple(map(float, p.strip().split())) for p in ring.split(",") if p.strip()]
            if len(points) >= 3: rings.append(points)
        if rings: polygons.append(Polygon(rings[0], rings[1:]))
    return polygon_only(MultiPolygon(polygons)) if polygons else None


def canonical_roster():
    """Normalize source depth independently of downloaded polygons."""
    with (RAW / "areacity_roster.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {r["id"]: r for r in rows}
    result = {}
    for row in rows:
        code = row["ext_id"][:6]
        if len(code) != 6 or code.startswith("0"): continue
        if code[:2] in {"71", "81", "82", "91"}: continue
        depth = int(row["deep"]); province = code[:2] + "0000"
        if depth == 0:
            level, parent = "province", "100000"
        elif depth == 1:
            if province in MUNICIPAL: continue
            level = "district" if len(row["id"]) == 6 else "city"
            parent = province
        else:
            parent_row = by_id[row["pid"]]
            if code == parent_row["ext_id"][:6]: continue
            level = "district"
            parent = province if province in MUNICIPAL else parent_row["ext_id"][:6]
        result[row["id"]] = {
            "id": code, "code": code, "code_system": "GB/T2260-compatible source code",
            "name": row["ext_name"], "parent": parent, "level": level,
            "source": "areacity_2026", "source_version": SOURCE_VERSION,
            "source_record": row["id"], "source_as_of": "2025-12-31 (publisher claim)",
            "verification": "third_party_snapshot", "aliases": [row["name"]],
            "coverage_status": "no_county_level_units" if code in TERMINAL_PREFECTURES else "county_unit" if level == "district" else "has_children",
            "admin_kind": "county" if level == "district" else "prefecture" if level == "city" else "province",
        }
    return result


def decode_topology(topology, key):
    scale, translate = topology["transform"]["scale"], topology["transform"]["translate"]
    arcs = []
    for raw in topology["arcs"]:
        x = y = 0; arc = []
        for dx, dy in raw:
            x += dx; y += dy
            arc.append([x*scale[0]+translate[0], y*scale[1]+translate[1]])
        arcs.append(arc)
    def ring(ids):
        result = []
        for arc_id in ids:
            points = arcs[arc_id] if arc_id >= 0 else list(reversed(arcs[~arc_id]))
            result.extend(points if not result else points[1:])
        if result and result[0] != result[-1]: result.append(result[0])
        return result
    for obj in topology["objects"][key]["geometries"]:
        coordinates = [ring(ids) for ids in obj["arcs"]] if obj["type"] == "Polygon" else [[ring(ids) for ids in polygon] for polygon in obj["arcs"]]
        yield obj["properties"], polygon_only(shape({"type": obj["type"], "coordinates": coordinates}))


def supplemental_regions():
    result = []
    provinces = json.loads((GEO / "raw" / "100000.json").read_text(encoding="utf-8"))["features"]
    for feature in provinces:
        p = feature["properties"]; code = str(p.get("adcode"))
        if code not in {"710000", "810000", "820000"}: continue
        props = {"id": code, "code": code, "name": p["name"], "level": "province", "parent": "100000", "source": "datav_snapshot",
                 "source_version": "original_project_snapshot", "verification": "source_date_unverified", "admin_kind": "province", "coverage_status": "has_children"}
        result.append((props, polygon_only(shape(feature["geometry"]))))
    for parent in ("810000", "820000"):
        source = json.loads((GEO / "raw" / f"{parent}.json").read_text(encoding="utf-8"))
        for feature in source["features"]:
            p = feature["properties"]
            props = {"id": str(p["adcode"]), "code": str(p["adcode"]), "name": p["name"], "level": "district", "parent": parent,
                     "source": "datav_snapshot", "source_version": "original_project_snapshot", "verification": "source_date_unverified",
                     "code_system": "DataV source identifier", "coverage_status": "county_analogue",
                     "admin_kind": "Hong_Kong_district" if parent == "810000" else "Macau_parish_or_local_area"}
            result.append((props, polygon_only(shape(feature["geometry"]))))
    topology = json.loads((RAW / "taiwan_atlas_towns.topo.json").read_text(encoding="utf-8"))
    for key, level in (("counties", "city"), ("towns", "district")):
        for p, geometry in decode_topology(topology, key):
            code = p["COUNTYCODE"] if key == "counties" else p["TOWNCODE"]
            original = p["COUNTYNAME"] if key == "counties" else p["TOWNNAME"]
            props = {"id": f"tw:{code}", "code": code, "code_system": "NLSC native code", "name": CC.convert(original).replace("臺", "台"),
                     "source_name": original, "level": level, "parent": "710000" if key == "counties" else f"tw:{p['COUNTYCODE']}",
                     "source": "taiwan_atlas", "source_version": "2021.9.20", "verification": "official_data_redistribution_older_snapshot",
                     "aliases": [original, CC.convert(original)], "admin_kind": "Taiwan_county_city" if key == "counties" else "Taiwan_township_district",
                     "coverage_status": "has_children" if key == "counties" else "county_analogue"}
            result.append((props, geometry))
    return result


def main():
    csv.field_size_limit(100_000_000)
    timestamp = datetime.now(timezone.utc).isoformat()
    backup = GEO / "backups" / "before_admin_upgrade"
    backup.mkdir(parents=True, exist_ok=True)
    for filename in ("province.json", "city.json", "district.json", "south_china_sea.json"):
        if not (backup / filename).exists(): shutil.copy2(GEO / filename, backup / filename)
    roster = canonical_roster(); geometry_by_id = {}
    with (RAW / "ok_geo.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["id"] not in roster: continue
            geometry = parse_polygon(row["polygon"])
            if geometry is not None and not geometry.is_empty:
                geometry_by_id[roster[row["id"]]["id"]] = geometry
    properties = {p["id"]: p for p in roster.values()}
    groups = defaultdict(list)
    for key, p in properties.items():
        if key in geometry_by_id: groups[(p["level"], p["parent"])].append(key)
    simplification = []
    for (level, parent), keys in groups.items():
        geometries = [geometry_by_id[k] for k in keys]
        tolerance = {"province": .012, "city": .004, "district": .0015}[level]
        shared = bool(coverage_is_valid(geometries))
        simplified = coverage_simplify(geometries, tolerance=tolerance) if shared else [g.simplify(tolerance, preserve_topology=True) for g in geometries]
        for key, geometry in zip(keys, simplified): geometry_by_id[key] = polygon_only(transform(geometry, gcj_to_wgs))
        simplification.append({"level": level, "parent": parent, "shared_edge_simplification": shared})
    for p, geometry in supplemental_regions():
        properties[p["id"]] = p; geometry_by_id[p["id"]] = geometry
    # Explicit omissions from the publisher. No guessed code or parent polygon.
    for identifier, name in (("pending:hean", "和安县"), ("pending:hekang", "和康县")):
        properties[identifier] = {"id": identifier, "code": None, "name": name, "parent": "653200", "level": "district", "source": "areacity_2026_release_notes",
                                  "source_version": SOURCE_VERSION, "verification": "code_and_geometry_pending", "admin_kind": "county",
                                  "coverage_status": "missing_geometry", "note": "数据源列出的新设县缺项：代码及真实边界待官方资料核验；不使用上级外框冒充县界。"}
    overrides = GEO / "reviewed_supplements.json"
    if overrides.exists():
        for feature in json.loads(overrides.read_text(encoding="utf-8"))["features"]:
            p = feature["properties"]
            if not p.get("source_url") or not p.get("source_as_of"): raise ValueError("Supplements require source_url and source_as_of")
            for old in p.get("replaces", []): properties.pop(old, None); geometry_by_id.pop(old, None)
            properties[p["id"]] = p; geometry_by_id[p["id"]] = polygon_only(shape(feature["geometry"]))
    children = defaultdict(list)
    for p in properties.values(): children[p["parent"]].append(p["id"])
    def ancestors(identifier):
        path, seen = [], set()
        while identifier in properties:
            if identifier in seen: raise ValueError(f"Parent cycle: {identifier}")
            seen.add(identifier); path.append(identifier); identifier = properties[identifier]["parent"]
        return list(reversed(path))
    features = {level: [] for level in LEVELS}; items = []
    for identifier, p in sorted(properties.items()):
        geometry = geometry_by_id.get(identifier); path = ancestors(identifier)
        item = {**p, "ancestor_ids": path[:-1], "full_name": " · ".join(properties[k]["name"] for k in path),
                "child_count": len(children[identifier]), "geometry_status": "available" if geometry is not None else "missing",
                "bbox": list(geometry.bounds) if geometry is not None else None,
                "geometry_hash": hashlib.sha256(geometry.wkb).hexdigest() if geometry is not None else None, "updated_at": timestamp}
        if geometry is not None:
            interior = geometry.representative_point(); item["label_point"] = [interior.x, interior.y]
            features[p["level"]].append({"type": "Feature", "properties": item, "bbox": item["bbox"], "geometry": mapping(geometry)})
        items.append(item)
    counts = dict(Counter(item["level"] for item in items))
    source_metadata = json.loads((RAW / "sources.json").read_text(encoding="utf-8"))
    version = hashlib.sha256(json.dumps([(i["id"],i["parent"],i["name"],i["geometry_hash"]) for i in items],ensure_ascii=False).encode()).hexdigest()[:16]
    stage = GEO / "build"; stage.mkdir(exist_ok=True)
    for level in LEVELS: dump(stage / f"{level}.json", {"type":"FeatureCollection", "features":features[level]})
    dump(stage / "admin_catalog.json", {"schema_version":2, "version":version, "built_at":timestamp, "counts":counts, "items":items})
    dump(stage / "admin_reference.json", {"version":version, "origin":"source roster plus explicitly known omissions", "items":[
        {k:p.get(k) for k in ("id", "code", "name", "parent", "level", "coverage_status", "source", "source_version")} for p in properties.values()]})
    limitations = [
        "大陆采用来源快照并保留版本、日期和哈希字段，目录接口返回来源版本信息。",
        "和安县、和康县在来源中无代码和边界，页面使用所属上级区域定位。",
        "台湾采用2021.9.20版官方资料再发布拓扑（22县市、368乡镇市区），并保留来源版本字段。",
        "港澳沿用原项目 DataV 分区快照，并保留来源时点字段。",
        "几何经过简化及GCJ-02近似反算，不用于测绘、法律边界或主权认定。",
    ]
    manifest = {"schema_version":2,"version":version,"built_at":timestamp,"target_standard":"现行县级及港澳台对应分区；附来源版本字段",
                "official_current_verified":False,"counts":counts,"sources":source_metadata,"limitations":limitations,
                "no_county_level_units":[{"id":k,"name":v} for k,v in TERMINAL_PREFECTURES.items()],
                "files":{f"{level}.json":{"sha256":digest(stage/f"{level}.json"),"features":len(features[level])} for level in LEVELS},"simplification":simplification}
    dump(stage / "admin_manifest.json", manifest, pretty=True)
    from audit_admin_bundle import audit
    report = audit(stage); dump(stage / "coverage_audit.json", report, pretty=True)
    if not report["structural_valid"]: raise RuntimeError(f"Invalid staged geography: {report}")
    for filename in ("province.json", "city.json", "district.json", "admin_catalog.json", "admin_reference.json", "admin_manifest.json", "coverage_audit.json"):
        (stage / filename).replace(GEO / filename)
    print(json.dumps({"version":version,"counts":counts,"available":len(geometry_by_id),"missing_geometry":report["missing_geometry"],"complete":report["complete"]},ensure_ascii=False))


if __name__ == "__main__": main()
