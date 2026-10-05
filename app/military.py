"""Sourced administrative carriers and discrete military arrival observations."""
from functools import lru_cache
import json
from pathlib import Path
from datetime import datetime, timedelta
import math
from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[1]
router = APIRouter()

@lru_cache(maxsize=8)
def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def stamp(value):
    text = str(value)
    if len(text) == 4: text += "-01-01"
    elif len(text) == 7: text += "-01"
    try: return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError: raise HTTPException(422, "日期格式错误")

def end_stamp(value):
    result = stamp(value)
    if len(value) == 10: return result + timedelta(days=1) - timedelta(microseconds=1)
    if len(value) == 7:
        return datetime(result.year + (result.month == 12), result.month % 12 + 1, 1) - timedelta(microseconds=1)
    if len(value) == 4: return datetime(result.year + 1, 1, 1) - timedelta(microseconds=1)
    return result

def observation_stamp(value):
    return end_stamp(value) if len(value) <= 7 else stamp(value)

@router.get("/api/military/sources")
def military_sources():
    return load("data/history/military-sources.json")

@router.get("/api/control")
def control(year: int = Query(1933, ge=1800, le=2100), bbox: str | None = None, at: str | None = None):
    moment = stamp(at) if at else datetime(year, 12, 31, 23, 59, 59)
    bounds = None
    if bbox:
        try:
            bounds = [float(v) for v in bbox.split(",")]
            if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds): raise ValueError()
            if not (-180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90): raise ValueError()
        except ValueError: raise HTTPException(422, "bbox需要西南东北四个数值")
    records = load("data/history/control-records.json")["records"]
    selected = [r for r in records if stamp(r["start_at"]) <= moment <= end_stamp(r["end_at"])]
    by_id = {}
    for level in {r["level"] for r in selected}:
        by_id.update({f["properties"]["id"]: f for f in load(f"data/geo/{level}.json")["features"]})
    features = []
    for record in selected:
        for admin_id in record["admin_ids"]:
            carrier = by_id.get(admin_id)
            if not carrier: continue
            box = carrier.get("bbox", carrier["properties"].get("bbox"))
            if bounds and box and (box[2] < bounds[0] or box[0] > bounds[2] or box[3] < bounds[1] or box[1] > bounds[3]): continue
            props = dict(record, admin_id=admin_id, name=carrier["properties"]["name"], geometry_role="modern_administrative_carrier")
            props.pop("admin_ids", None)
            features.append({"type":"Feature", "id":f"{record['id']}:{admin_id}", "properties":props, "geometry":carrier["geometry"]})
    return {"type":"FeatureCollection", "features":features, "at":moment.isoformat(), "sources":military_sources(), "coverage_note":"未有可靠范围记录的地区保持中性；现代行政面只作地点范围载体，并非复原历史疆界"}

@router.get("/api/units")
def units(year: int | None = Query(None, ge=1800, le=2100), q: str = "", category: str | None = None, battle_id: str | None = None):
    items = load("data/history/unit-movements.json")["units"]
    if category:
        items = [u for u in items if category in u.get("categories", [])]
    if battle_id:
        items = [u for u in items if battle_id in u.get("battle_ids", [])]
    return {"units":[u for u in items if (year is None or int(u["start_at"][:4]) <= year <= int(u["end_at"][:4])) and q.casefold() in u["name"].casefold()]}

@router.get("/api/units/{unit_id}/timeline")
def timeline(unit_id: str, at: str | None = None):
    unit = next((u for u in load("data/history/unit-movements.json")["units"] if u["id"] == unit_id), None)
    if unit is None: raise HTTPException(404, "未找到部队")
    moment = stamp(at) if at else end_stamp(unit["end_at"])
    arrivals = [w for w in unit["waypoints"] if observation_stamp(w["at"]) <= moment]
    last = arrivals[-1] if arrivals else None
    current = last if last and stamp(last["at"]) <= moment <= end_stamp(last["at"]) else None
    return {"unit_id":unit_id, "name":unit["name"], "faction":unit["faction"], "at":moment.isoformat(), "position":current, "last_arrival":last, "arrivals":arrivals, "waypoints":unit["waypoints"], "coordinates":[w["coords"] for w in arrivals], "granularity":unit["granularity"], "route_kind":"dated_arrival_observations", "interpolate":False, "precision_note":unit["precision_note"]}
