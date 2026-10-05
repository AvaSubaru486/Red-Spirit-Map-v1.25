from __future__ import annotations

import json
import hashlib
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.history import router as history_router
from app.admin import router as admin_router, catalog_index, compact, document
from app.ai import router as ai_router
from app.military import router as military_router


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
PROJECT_ID = hashlib.sha256(str(ROOT.resolve()).casefold().encode("utf-8")).hexdigest()

app = FastAPI(title="红色精神全国离线历史地图", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://avasubaru486.github.io",
        "http://127.0.0.1:8010",
        "http://localhost:8010",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_middleware(GZipMiddleware, minimum_size=1200)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(history_router)
app.include_router(admin_router)
app.include_router(ai_router)
app.include_router(military_router)


@lru_cache(maxsize=16)
def read_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_data(name: str, default: Any) -> Any:
    path = DATA_DIR / name
    return read_json(str(path)) if path.exists() else default


def decorate_event(item: dict[str, Any]) -> dict[str, Any]:
    """Attach a traceable offline source index to legacy event records."""
    result = dict(item)
    source_ids = list(result.get("source_ids") or ["chronicle"])
    result["source_ids"] = source_ids
    catalog_path = DATA_DIR / "history" / "sources.json"
    catalog = read_json(str(catalog_path)) if catalog_path.exists() else {}
    result["sources"] = [catalog[key] for key in dict.fromkeys(source_ids) if key in catalog]
    return result


def event_matches(
    item: dict[str, Any],
    mode: str,
    year: int | None,
    person: str | None,
    region: str | None,
    kind: str | None,
) -> bool:
    if mode == "long_march" and "long_march" not in item.get("themes", []):
        return False
    if mode == "anti_japanese" and "anti_japanese" not in item.get("themes", []):
        return False
    if mode == "time" and year is not None and item.get("year") != year:
        return False
    if mode == "person" and person and person not in item.get("people", []):
        return False
    if year is not None and mode != "time" and item.get("year") != year:
        return False
    if region and region not in {item.get("province"), item.get("city"), item.get("district")}:
        return False
    if kind and item.get("kind") != kind:
        return False
    return True


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health(response: Response) -> dict[str, str]:
    # Let the launcher distinguish this project from another local HTTP service.
    response.headers["X-Red-Map-Project"] = PROJECT_ID
    return {"status": "ok", "mode": "offline"}


@app.get("/api/events")
def events(
    mode: Literal["ordinary", "long_march", "anti_japanese", "time", "person"] = "ordinary",
    year: int | None = Query(default=None, ge=1921, le=2100),
    person: str | None = None,
    region: str | None = None,
    kind: Literal["event", "residence", "site", "memorial", "building"] | None = None,
) -> dict[str, Any]:
    source = load_data("events.json", [])
    result = [
        decorate_event(item)
        for item in source
        if event_matches(item, mode, year, person, region, kind)
    ]
    return {"items": result, "count": len(result), "mode": mode, "year": year}


@app.get("/api/events/{event_id}")
def event(event_id: str) -> dict[str, Any]:
    source = load_data("events.json", [])
    for item in source:
        if item.get("id") == event_id:
            return decorate_event(item)
    raise HTTPException(status_code=404, detail="未找到该历史内容")


@app.get("/api/persons")
def persons() -> dict[str, Any]:
    return {"items": load_data("persons.json", [])}


@app.get("/api/routes/{mode}")
def routes(mode: Literal["ordinary", "long_march", "anti_japanese", "person"]) -> dict[str, Any]:
    source = load_data("routes.json", {})
    return {"routes": source.get(mode, [])}


def geometry_bounds(geometry: dict[str, Any]) -> list[float]:
    """Bounds use every vertex, not a region's centre (islands are retained)."""
    west = south = math.inf
    east = north = -math.inf

    def visit(coordinates: list) -> None:
        nonlocal west, south, east, north
        if not coordinates:
            return
        if isinstance(coordinates[0], (int, float)):
            x, y = coordinates[:2]
            west, south = min(west, x), min(south, y)
            east, north = max(east, x), max(north, y)
        else:
            for child in coordinates:
                visit(child)

    visit(geometry.get("coordinates", []))
    return [west, south, east, north]


@lru_cache(maxsize=8)
def indexed_geometry(level: str, modified: int, size: int) -> list[dict[str, Any]]:
    # The key includes the source fingerprint, so regenerated local boundaries
    # do not need a manual index rebuild or stale hand-maintained manifest.
    path = DATA_DIR / "geo" / f"{level}.json"
    with path.open(encoding="utf-8") as handle:
        source = json.load(handle)
    return [{**feature, "bbox": geometry_bounds(feature["geometry"])} for feature in source["features"]]


def geometry_features(level: str) -> list[dict[str, Any]]:
    path = DATA_DIR / "geo" / f"{level}.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"本地{level}边界暂不可用，请先运行 scripts/download_boundaries.py")
    stamp = path.stat()
    return indexed_geometry(level, stamp.st_mtime_ns, stamp.st_size)


def display_geometry_features(level: str) -> list[dict[str, Any]]:
    """Complete display coverage without changing canonical administrative rank."""
    features = geometry_features(level)
    if level == "city":
        # Municipalities/SARs have no intervening prefecture; provincially
        # administered counties are shown as counties, never fabricated cities.
        features = [*features,
            *[{**f,"properties":{**f["properties"],"display_role":"direct_province"}} for f in geometry_features("province") if f["properties"]["id"] in {"110000","120000","310000","500000","810000","820000"}],
            *[f for f in geometry_features("district") if f["properties"]["parent"] in {"410000","420000","460000","650000"}]]
    elif level == "district":
        features = [*features,*[{**f,"properties":{**f["properties"],"display_role":"terminal_city"}} for f in geometry_features("city") if f["properties"].get("coverage_status")=="no_county_level_units"]]
    return features


def parse_bbox(value: str) -> list[float]:
    try:
        bounds = [float(part) for part in value.split(",")]
        if len(bounds) != 4 or not all(math.isfinite(part) for part in bounds):
            raise ValueError
        west, south, east, north = bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError
        return bounds
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="bbox 必须是有效的西、南、东、北四个经纬度") from None


def bounds_intersect(first: list[float], second: list[float]) -> bool:
    return first[0] <= second[2] and first[2] >= second[0] and first[1] <= second[3] and first[3] >= second[1]


@app.get("/api/geo-index")
def geo_index() -> JSONResponse:
    # Names, hierarchy and bounds only. County geometry stays viewport-loaded.
    return JSONResponse({
        level: [compact(item) for item in catalog_index().values() if item["level"]==level]
        for level in ("province", "city", "district")
    }, headers={"X-Geo-Version":document("admin_catalog.json")["version"]})


@lru_cache(maxsize=4)
def world_features(modified: int, size: int) -> list[dict[str, Any]]:
    path = DATA_DIR / "geo" / "world.json"
    with path.open(encoding="utf-8") as handle:
        source = json.load(handle)
    return [{**feature, "bbox": geometry_bounds(feature["geometry"])} for feature in source["features"]]


@app.get("/api/geo/world")
def world_geo(
    bbox: str | None = Query(default=None, max_length=160),
) -> JSONResponse:
    """Serve the bundled low-resolution world basemap without network tiles."""
    path = DATA_DIR / "geo" / "world.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail="本地世界底图暂不可用")
    bounds = parse_bbox(bbox) if bbox is not None else None
    stamp = path.stat()
    features = world_features(stamp.st_mtime_ns, stamp.st_size)
    selected = [feature for feature in features if bounds_intersect(feature["bbox"], bounds)] if bounds else features
    manifest_path = DATA_DIR / "geo" / "world_manifest.json"
    manifest = read_json(str(manifest_path)) if manifest_path.exists() else {}
    return JSONResponse({
        "type": "FeatureCollection",
        "features": selected,
        "source_count": len(features),
        "version": manifest.get("version", "bundled-world-1"),
        "source": manifest,
    }, headers={"X-Geo-Version": manifest.get("version", "bundled-world-1")})


@app.get("/api/geo/{level}")
def geo(
    level: Literal["province", "city", "district", "south_china_sea"],
    bbox: str | None = Query(default=None, max_length=160),
) -> JSONResponse:
    bounds = parse_bbox(bbox) if bbox is not None else None
    features = display_geometry_features(level)
    selected = [feature for feature in features if bounds_intersect(feature["bbox"], bounds)] if bounds else features
    # Bypass FastAPI's recursive dict validation for large coordinate arrays.
    # No bbox still returns ALL original features for compatibility/export.
    return JSONResponse({"type": "FeatureCollection", "features": selected, "source_count": len(features),
                         "canonical_count":len(geometry_features(level)),"version":document("admin_catalog.json")["version"]})


@app.get("/api/regions/{region_id}/stories")
def region_stories(region_id: str, year: int | None = Query(None, ge=1860, le=2100)) -> dict[str, Any]:
    source = load_data("events.json", [])
    index = catalog_index()
    item = index.get(region_id)
    name = item["name"] if item else region_id
    def in_region(event):
        if name not in {event.get("province"),event.get("city"),event.get("district")}:
            return False
        # Code lookup disambiguates repeated county names by province. Existing
        # name-based API calls intentionally keep their original behaviour.
        if item and item["ancestor_ids"]:
            province = index[item["ancestor_ids"][0]]["name"]
            return event.get("province") == province
        return True
    items = [
        item
        for item in source
        if in_region(item)
        and (year is None or item.get("year") == year)
    ]
    return {"region": region_id, "items": items, "count": len(items)}
