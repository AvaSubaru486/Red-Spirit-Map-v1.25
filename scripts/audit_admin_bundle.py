"""Strict reference/geometry audit; incomplete source data can never pass."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data" / "geo"
LEVELS = ("province", "city", "district")
TERMINAL = {"441900", "442000", "460400", "620200"}


def audit(directory=GEO):
    def read(name): return json.loads((directory / name).read_text(encoding="utf-8"))
    catalog=read("admin_catalog.json");reference=read("admin_reference.json");manifest=read("admin_manifest.json")
    items,refs=catalog["items"],reference["items"]
    counts=Counter(i["id"] for i in items);by_id={i["id"]:i for i in items};expected={i["id"]:i for i in refs}
    code_counts=Counter((i.get("code_system",""),i["code"]) for i in items if i.get("code"))
    duplicate_codes=[{"code_system":system,"code":code} for (system,code),n in code_counts.items() if n>1]
    duplicate_reference_ids=[key for key,n in Counter(i["id"] for i in refs).items() if n>1]
    invalid,empty,mismatches,duplicates_geometry,hashes,features=[],[],[],[],[],{}
    geometry_property_errors=[]
    file_counts={}
    for level in LEVELS:
        filename=f"{level}.json";data=read(filename)["features"];file_counts[level]=len(data)
        with (directory/filename).open("rb") as f:file_hash=hashlib.file_digest(f,"sha256").hexdigest()
        if file_hash!=manifest["files"][filename]["sha256"]:hashes.append(filename)
        for f in data:
            p=f["properties"];key=p["id"]
            if key in features:duplicates_geometry.append(key)
            features[key]=f
            if p.get("coverage")=="city_fallback" or p["level"]!=level or "_city_coverage" in key:mismatches.append(key)
            item=by_id.get(key)
            if not item or any(p.get(k)!=item.get(k) for k in ("name","parent","level","full_name","coverage_status")):
                geometry_property_errors.append(key)
            try:
                geometry=shape(f["geometry"])
                if geometry.is_empty:empty.append(key)
                elif not geometry.is_valid or geometry.geom_type not in {"Polygon","MultiPolygon"} or not all(math.isfinite(n) for n in geometry.bounds):invalid.append(key)
                elif geometry.bounds[0]<-180 or geometry.bounds[2]>180 or geometry.bounds[1]<-90 or geometry.bounds[3]>90:invalid.append(key)
                if item and item.get("geometry_hash")!=hashlib.sha256(geometry.wkb).hexdigest():geometry_property_errors.append(key)
                if not geometry.is_empty and (list(geometry.bounds)!=f.get("bbox") or (item and list(geometry.bounds)!=item.get("bbox"))):geometry_property_errors.append(key)
            except (KeyError,ValueError,TypeError):invalid.append(key)
    orphan=[i["id"] for i in items if i["parent"]!="100000" and i["parent"] not in by_id]
    reference_mismatches=[key for key in expected.keys()&by_id.keys() if any(expected[key].get(k)!=by_id[key].get(k) for k in ("name","parent","level"))]
    child_counts=Counter(i["parent"] for i in items)
    for item in items:
        path,seen=[],set();key=item["id"]
        while key in by_id:
            if key in seen:mismatches.append(item["id"]);break
            seen.add(key);path.append(key);key=by_id[key]["parent"]
        if item.get("ancestor_ids")!=list(reversed(path))[0:-1]:mismatches.append(item["id"])
        child_count=child_counts[item["id"]]
        if child_count!=item["child_count"]:mismatches.append(item["id"])
        if item.get("coverage_status")=="no_county_level_units" and (item["id"] not in TERMINAL or child_count):mismatches.append(item["id"])
        if item["level"] in {"province","city"} and not child_count and item["id"] not in TERMINAL:mismatches.append(item["id"])
        if (item["geometry_status"]=="available")!=(item["id"] in features):mismatches.append(item["id"])
    missing=[{"id":key,"name":p["name"],"parent":p["parent"],"source":p.get("source")} for key,p in expected.items() if key not in features]
    missing_catalog=sorted(expected.keys()-by_id.keys());unexpected_catalog=sorted(by_id.keys()-expected.keys());duplicates=sorted(k for k,n in counts.items() if n>1)
    structural=not any((duplicates,duplicate_codes,duplicate_reference_ids,duplicates_geometry,orphan,invalid,empty,mismatches,hashes,reference_mismatches,missing_catalog,unexpected_catalog,geometry_property_errors))
    return {"schema_version":2,"version":catalog["version"],"province_count":file_counts["province"],"city_count":file_counts["city"],"district_count":file_counts["district"],
            "catalog_count":len(items),"expected_count":len(refs),"available_geometry_count":len(features),"missing_geometry":missing,
            "missing_catalog":missing_catalog,"unexpected_catalog":unexpected_catalog,"duplicate_ids":duplicates,"duplicate_codes":duplicate_codes,
            "duplicate_reference_ids":duplicate_reference_ids,"duplicate_geometry_ids":duplicates_geometry,"geometry_property_errors":sorted(set(geometry_property_errors)),
            "orphan_parents":orphan,"empty_geometry":empty,"invalid_geometry":invalid,"hierarchy_or_status_errors":sorted(set(mismatches)),
            "reference_mismatches":reference_mismatches,"hash_mismatches":hashes,"structural_valid":structural,
            "snapshot_complete":structural and not missing,"official_current_verified":manifest["official_current_verified"],
            "complete":structural and not missing and manifest["official_current_verified"],
            "no_county_level_units":manifest["no_county_level_units"],"limitations":manifest["limitations"]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--allow-incomplete",action="store_true");args=parser.parse_args()
    report=audit();(GEO/"coverage_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if not report["structural_valid"] or (not args.allow_incomplete and not report["complete"]):raise SystemExit(1)


if __name__ == "__main__":main()
