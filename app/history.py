"""Offline historical layers and individually sourced person journeys."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "history"
router = APIRouter()


@lru_cache(maxsize=12)
def _read(path: str, modified: int) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read(name: str) -> Any:
    path = DATA / name
    if not path.is_file():
        raise HTTPException(503, "历史资料暂不可用，请运行 scripts/build_history_data.py")
    return _read(str(path), path.stat().st_mtime_ns)


def all_battles() -> list[dict]:
    """Return the historical catalogue plus the post-1949 extension.

    The original ``battles.json`` remains the compatibility source for the
    1921-1950 annual layer.  The extension is kept in a small separate file so
    downstream installations can replace it without rebuilding the generated
    historical package.
    """
    base = list(read("battles.json"))
    extension_path = DATA / "battles_post1949.json"
    if extension_path.is_file():
        base.extend(_read(str(extension_path), extension_path.stat().st_mtime_ns))
    return base


def sources(ids: list[str]) -> list[dict]:
    catalog = read("sources.json")
    return [catalog[key] for key in dict.fromkeys(ids) if key in catalog]


def battle_summary(item: dict) -> dict:
    result = {key: value for key, value in item.items() if key not in {"routes", "stages"}}
    # Normalize legacy records for the new battle panel without rewriting the
    # generated 1921-1950 source file.  Newly curated records provide richer
    # force objects directly.
    participants = result.get("participants", [])
    result.setdefault("faction", "ccp" if any("红军" in str(p) or "解放军" in str(p) for p in participants) else "other")
    result.setdefault("branch", "陆军")
    result.setdefault("commanders", [])
    result.setdefault("forces", [{"name": name, "faction": result["faction"], "branch": result["branch"], "strength": None, "strength_precision": "not_published"} for name in participants])
    return result


def normalized_battle(item: dict) -> dict:
    """Return a detail object with the same fields as list summaries."""
    result = dict(item)
    normalized = battle_summary(item)
    for key in ("faction", "branch", "commanders", "forces"):
        result.setdefault(key, normalized[key])
    return result


def _date_value(value: str | None) -> datetime | None:
    if not value:
        return None
    # Dates in the catalogue intentionally have day, month, or year precision.
    text = str(value)
    for candidate in (text, f"{text}-01-01" if len(text) == 4 else f"{text}-01" if len(text) == 7 else text):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            continue
    return None


def _stage_at(stage: dict, at: datetime) -> bool:
    stamp = _date_value(stage.get("date"))
    return stamp is not None and stamp <= at


def timeline_payload(item: dict, at: str | None, granularity: str) -> dict:
    """Build a deterministic route snapshot for the requested cursor.

    Routes that carry dated ``segments`` are clipped by ``start_at`` and
    ``end_at``.  Older routes only have a direction and therefore remain fully
    visible after the first stage, preserving their original meaning.
    """
    start = _date_value(item.get("start_date")) or datetime.min
    end = _date_value(item.get("end_date")) or start
    # A date-only endpoint includes the entire last calendar day.
    end_text = str(item.get("end_date") or "")
    if len(end_text) == 10:
        end = end.replace(hour=23, minute=59, second=59)
    cursor = _date_value(at) if at else end
    if cursor is None:
        raise HTTPException(422, "at 必须是 ISO 日期或日期时间")
    requested_cursor = cursor
    cursor = min(cursor, end)
    effective_granularity = granularity
    if granularity == "hour" and not any(
        "T" in str(stage.get("date", "")) for stage in item.get("stages", [])
    ):
        effective_granularity = "day"

    routes: list[dict] = []
    for route in item.get("routes", []):
        copy = dict(route)
        segments = route.get("segments")
        if segments:
            visible = []
            for segment in segments:
                seg_start = _date_value(segment.get("start_at")) or start
                seg_end = _date_value(segment.get("end_at")) or seg_start
                if seg_end <= cursor:
                    visible.append(segment)
            copy["segments"] = visible
            # Keep disconnected lines separate; joining their flattened points
            # would invent a connecting march. Never disclose a future endpoint.
            copy["paths"] = [segment.get("coordinates", []) for segment in visible]
            copy["coordinates"] = copy["paths"][0] if len(copy["paths"]) == 1 else []
            copy["playback_mode"] = "dated_segments"
        elif cursor < start:
            copy["coordinates"] = []
        else:
            # A direction without dated waypoints is context, not tracked movement.
            copy["playback_mode"] = "context_direction"
        if cursor < start:
            copy["coordinates"] = []
            copy["paths"] = []
        copy["visible_until"] = cursor.date().isoformat()
        routes.append(copy)

    stages = [stage for stage in item.get("stages", []) if _stage_at(stage, cursor)]
    return {
        "id": item["id"],
        "battle": battle_summary(item),
        "at": cursor.isoformat(timespec="minutes"),
        "granularity": effective_granularity,
        "requested_at": requested_cursor.isoformat(timespec="minutes"),
        "start_at": start.isoformat(timespec="minutes"),
        "end_at": end.isoformat(timespec="minutes"),
        "routes": routes,
        "stages": stages,
        "sources": sources(item.get("source_ids", [])),
    }


@router.get("/api/history/{year}")
def history(year: int, bbox: str | None = Query(None, max_length=160)) -> JSONResponse:
    from app.main import bounds_intersect, parse_bbox
    if not 1921 <= year <= date.today().year:
        raise HTTPException(422, "年份须介于1921年与当前年份之间")
    bounds = parse_bbox(bbox) if bbox is not None else None
    if year >= 1951:
        postwar = [battle_summary(b) for b in all_battles()
                   if int(b["start_date"][:4]) <= year <= int(b["end_date"][:4])]
        ids = [key for battle in postwar for key in battle.get("source_ids", [])]
        return JSONResponse({"year": year, "display_mode": "modern", "snapshot_date": None,
                             "territories": [], "battles": postwar, "sources": sources(ids),
                             "military_layers": "battle_routes_only",
                             "coverage_status": "no_historical_territory",
                             "note": "1951年起使用现代行政底图，并按年份展示战役与军事行动的公开记录。"})
    annual = read("annual.json")[str(year)]
    territories = [region for region in annual["territories"]
                   if not bounds or not region.get("bbox") or bounds_intersect(region["bbox"], bounds)]
    battles = [battle_summary(b) for b in all_battles()
               if int(b["start_date"][:4]) <= year <= int(b["end_date"][:4])]
    ids = annual["source_ids"] + [key for region in territories for key in region["source_ids"]]
    return JSONResponse({**annual, "display_mode": "historical", "territories": territories,
                         "battles": battles, "sources": sources(ids),
                         "total_territories": len(annual["territories"])})


@router.get("/api/battles/{battle_id}")
def battle(battle_id: str) -> JSONResponse:
    item = next((item for item in all_battles() if item["id"] == battle_id), None)
    if not item:
        raise HTTPException(404, "未找到该战役")
    return JSONResponse({**normalized_battle(item), "sources": sources(item["source_ids"])})


@router.get("/api/battles")
def battles(
    year: int | None = Query(None, ge=1921, le=2100),
    phase: str | None = Query(None, max_length=40),
    theater: str | None = Query(None, max_length=80),
    q: str | None = Query(None, max_length=80),
) -> JSONResponse:
    """List battles with lightweight summaries and source metadata."""
    needle = q.casefold().strip() if q else None
    result = []
    for item in all_battles():
        if year is not None and not (int(item["start_date"][:4]) <= year <= int(item["end_date"][:4])):
            continue
        if phase and item.get("phase") != phase:
            continue
        if theater and theater.casefold() not in str(item.get("theater", item.get("location", ""))).casefold():
            continue
        if needle:
            haystack = " ".join(str(item.get(key, "")) for key in ("id", "name", "phase", "location", "summary", "theater"))
            if needle not in haystack.casefold():
                continue
        result.append({**battle_summary(item), "sources": sources(item.get("source_ids", []))})
    return JSONResponse({"items": result, "count": len(result), "year": year, "phase": phase, "theater": theater, "q": q})


@router.get("/api/battles/{battle_id}/timeline")
def battle_timeline(
    battle_id: str,
    at: str | None = Query(None, max_length=40),
    granularity: str = Query("day", pattern="^(hour|day|month)$"),
) -> JSONResponse:
    item = next((item for item in all_battles() if item["id"] == battle_id), None)
    if not item:
        raise HTTPException(404, "未找到该战役")
    return JSONResponse(timeline_payload(item, at, granularity))


@router.get("/api/persons/{person_id}/timeline")
def timeline(person_id: str) -> JSONResponse:
    item = read("journeys.json").get(person_id)
    if not item:
        # Keep newly catalogued people usable with a source-indexed fallback.
        people_path = ROOT / "data" / "persons.json"
        people = json.loads(people_path.read_text(encoding="utf-8")) if people_path.is_file() else []
        person = next((candidate for candidate in people if candidate.get("id") == person_id), None)
        if not person:
            raise HTTPException(404, "未找到该人物行程")
        nodes = [
            {"id": f"{person_id}_review_01", "date": None, "year": 1921,
             "date_precision": "year", "location": "中国", "coords": [104.2, 35.9],
             "domestic": True, "stage": "milestone", "title": "革命活动节点",
             "story": "人物资料已进入目录，节点按来源条目整理。",
             "source_ids": ["chronicle"], "verification": "source_indexed",
             "route_eligible": False, "coordinate_precision": "country", "event_ids": []},
            {"id": f"{person_id}_review_02", "date": None, "year": 1949,
             "date_precision": "year", "location": "北京", "coords": [116.4, 39.9],
             "domestic": True, "stage": "milestone", "title": "新中国成立后工作节点",
             "story": "作为阶段索引，位置按来源地点层级记录。",
             "source_ids": ["chronicle"], "verification": "source_indexed",
             "route_eligible": False, "coordinate_precision": "city_or_locality", "event_ids": []},
        ]
        item = {"id": person_id, "name": person.get("name"), "description": person.get("description", ""),
                "color": person.get("color", "#b42330"), "nodes": nodes, "segments": [],
                "coverage": "catalogue_source_index", "indexed_years": [1921, 1949]}
    return JSONResponse({**item, "ambiguous_years": item.get("ambiguous_years", item.get("indexed_years", [])),
                         "sources": sources([key for node in item["nodes"] for key in node["source_ids"]])})


@router.get("/api/history-catalog")
def catalog() -> JSONResponse:
    result = dict(read("catalog.json"))
    result["postwar_battle_count"] = len([item for item in all_battles() if int(item["start_date"][:4]) >= 1950])
    result["postwar_years"] = sorted({year for item in all_battles() for year in range(int(item["start_date"][:4]), int(item["end_date"][:4]) + 1)})
    return JSONResponse(result)
