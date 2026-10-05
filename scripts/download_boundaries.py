"""Download and simplify local administrative boundaries.

This script is intentionally explicit about its output directory: every generated
file lives under the project on D:. It uses the DataV administrative boundary
service only while preparing the offline bundle; the application never calls it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "geo" / "raw"
OUT = DATA / "geo"
BASE_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json"
TAIWAN_COUNTY_URL = "https://cdn.jsdelivr.net/gh/g0v/twgeojson@master/json/twCounty2010.geo.json"
TAIWAN_TOWN_URL = "https://cdn.jsdelivr.net/gh/g0v/twgeojson@master/json/twTown1982.geo.json"


def fetch(code: int) -> dict:
    target = RAW / f"{code}.json"
    if target.exists() and target.stat().st_size > 0:
        return json.loads(target.read_text(encoding="utf-8"))
    request = Request(BASE_URL.format(code=code), headers={"User-Agent": "red-spirit-map-builder/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            payload = response.read()
    except (HTTPError, URLError):
        return {"type": "FeatureCollection", "features": []}
    target.write_bytes(payload)
    time.sleep(0.05)
    return json.loads(payload.decode("utf-8"))


def fetch_external(url: str, filename: str) -> dict:
    """Fetch an auxiliary boundary dataset into the D: drive cache."""
    target = RAW / filename
    if target.exists() and target.stat().st_size > 0:
        return json.loads(target.read_text(encoding="utf-8"))
    request = Request(url, headers={"User-Agent": "red-spirit-map-builder/1.0"})
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read()
    except (HTTPError, URLError):
        return {"type": "FeatureCollection", "features": []}
    target.write_bytes(payload)
    return json.loads(payload.decode("utf-8"))


def simplify_line(points: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(points) <= 4:
        return points
    kept = [points[0]]
    last = points[0]
    for point in points[1:-1]:
        if abs(point[0] - last[0]) + abs(point[1] - last[1]) >= tolerance:
            kept.append(point)
            last = point
    kept.append(points[-1])
    return kept


def simplify_geometry(geometry: dict, tolerance: float) -> dict:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        coordinates = [simplify_line(ring, tolerance) for ring in coordinates]
    elif kind == "MultiPolygon":
        coordinates = [[simplify_line(ring, tolerance) for ring in polygon] for polygon in coordinates]
    elif kind == "LineString":
        coordinates = simplify_line(coordinates, tolerance)
    elif kind == "MultiLineString":
        coordinates = [simplify_line(line, tolerance) for line in coordinates]
    return {**geometry, "coordinates": coordinates}


def normalize_feature(feature: dict, level: str, tolerance: float) -> dict:
    properties = feature.get("properties", {})
    properties = {
        "id": str(properties.get("adcode", properties.get("name", "unknown"))),
        "name": properties.get("name") or "南海区域",
        "level": level,
        "center": properties.get("center") or properties.get("centroid"),
        "parent": str(properties.get("parent", {}).get("adcode", "100000")),
    }
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": simplify_geometry(feature.get("geometry", {}), tolerance),
    }


def write_collection(name: str, features: list[dict]) -> None:
    payload = {"type": "FeatureCollection", "features": features}
    (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def add_taiwan_boundaries(cities: list[dict], districts: list[dict]) -> None:
    """Add Taiwan's county/city and township/district boundaries.

    The main administrative service has no 710000 payload.  The local Taiwan
    GeoJSON fallback keeps the province visible while supplying the missing
    two lower levels for offline zooming.
    """
    county_payload = fetch_external(TAIWAN_COUNTY_URL, "taiwan_county.geo.json")
    town_payload = fetch_external(TAIWAN_TOWN_URL, "taiwan_town.geo.json")
    counties = county_payload.get("features", [])
    towns = town_payload.get("features", [])
    if not counties or not towns:
        return

    county_ids: dict[str, str] = {}
    for feature in counties:
        properties = feature.get("properties", {})
        county_id = str(properties.get("COUNTYSN") or properties.get("id") or "")
        name = properties.get("name") or properties.get("COUNTYNAME")
        if not county_id or not name:
            continue
        county_ids[str(name)] = county_id
        cities.append(normalize_feature({**feature, "properties": {**properties, "adcode": county_id, "name": name, "parent": {"adcode": "710000"}}}, "city", 0.012))

    for feature in towns:
        properties = feature.get("properties", {})
        town_id = str(properties.get("TOWNSN") or properties.get("id") or "")
        name = properties.get("name") or properties.get("TOWNNAME")
        parent_id = county_ids.get(str(properties.get("COUNTYNAME") or ""))
        if not town_id or not name or not parent_id:
            continue
        districts.append(normalize_feature({**feature, "properties": {**properties, "adcode": town_id, "name": name, "parent": {"adcode": parent_id}}}, "district", 0.004))


def add_city_coverage(cities: list[dict], districts: list[dict]) -> None:
    """Add an explicit city outline where no county-level unit exists.

    These are not invented districts: they reuse the official city geometry
    and are explicitly marked so the browser renders the city name instead of
    pretending that a detailed district boundary is available.
    """
    district_parents = {str(feature.get("properties", {}).get("parent", "")) for feature in districts}
    for city in cities:
        properties = city.get("properties", {})
        city_id = str(properties.get("id", ""))
        # Missing downloads are not evidence of a terminal city. Only these
        # explicitly documented prefectures have no county-level children.
        if city_id not in {"441900", "442000", "460400", "620200"} or city_id in district_parents:
            continue
        districts.append({
            "type": "Feature",
            "properties": {
                "id": city_id,
                "name": properties.get("name", "市"),
                "level": "city",
                "parent": str(properties.get("parent", "100000")),
                "coverage_status": "no_county_level_units",
                "coverage_parent": city_id,
                "center": properties.get("center"),
                "source": "city_geometry_coverage",
            },
            "geometry": city.get("geometry", {}),
        })


def main() -> None:
    # Do not let the legacy importer overwrite the audited live bundle with
    # outdated hierarchy and guessed terminal cities. The raw cache remains
    # available to the new builder for special-region geometry.
    if (OUT / "admin_reference.json").exists():
        from fetch_admin_sources import main as fetch_sources
        from rebuild_admin_boundaries import main as rebuild
        fetch_sources()
        rebuild()
        return
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    base = fetch(100000)
    province_features = [f for f in base["features"] if f.get("properties", {}).get("level") == "province"]
    write_collection("province", [normalize_feature(f, "province", 0.035) for f in province_features])
    jd = [f for f in base["features"] if f.get("properties", {}).get("adchar") == "JD"]
    write_collection("south_china_sea", [normalize_feature(f, "sea", 0.01) for f in jd])

    cities: list[dict] = []
    districts: list[dict] = []
    for province in province_features:
        province_code = int(province["properties"]["adcode"])
        children = fetch(province_code).get("features", [])
        child_levels = {f.get("properties", {}).get("level") for f in children}
        if "city" in child_levels:
            for city in children:
                if city.get("properties", {}).get("level") != "city":
                    continue
                cities.append(normalize_feature(city, "city", 0.018))
                city_code = int(city["properties"]["adcode"])
                for district in fetch(city_code).get("features", []):
                    if district.get("properties", {}).get("level") == "district":
                        districts.append(normalize_feature(district, "district", 0.006))
        else:
            for district in children:
                if district.get("properties", {}).get("level") == "district":
                    districts.append(normalize_feature(district, "district", 0.006))
    add_taiwan_boundaries(cities, districts)
    # Display-only terminal city outlines are now added by the API. Never write
    # them into the canonical county geometry file.
    write_collection("city", cities)
    write_collection("district", districts)
    print(f"province={len(province_features)} city={len(cities)} district={len(districts)}")


if __name__ == "__main__":
    main()
