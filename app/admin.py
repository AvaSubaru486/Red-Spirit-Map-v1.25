"""Local catalogue queries. No network or geometry processing at runtime."""
from __future__ import annotations
import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

GEO = Path(__file__).resolve().parents[1] / "data" / "geo"
router = APIRouter()


@lru_cache(maxsize=8)
def _read(name: str, stamp: int, size: int):
    return json.loads((GEO / name).read_text(encoding="utf-8"))


def document(name: str):
    path = GEO / name
    if not path.exists(): raise HTTPException(503, "行政区数据暂不可用，请运行 scripts/build_admin_catalog.py")
    stat=path.stat()
    return _read(name,stat.st_mtime_ns,stat.st_size)


@lru_cache(maxsize=2)
def _catalog_index(version):
    data=document("admin_catalog.json")
    return {item["id"]:item for item in data["items"]}


def catalog_index():
    return _catalog_index(document("admin_catalog.json")["version"])


def region(identifier):
    item=catalog_index().get(identifier)
    if not item: raise HTTPException(404,"未找到该行政区")
    return item


def search_text(value):
    return unicodedata.normalize("NFKC", value).replace("臺", "台").casefold()


def compact(item):
    keys=("id","code","name","level","parent","full_name","ancestor_ids","bbox","label_point","child_count","geometry_status","coverage_status","aliases")
    return {key:item.get(key) for key in keys}


@router.get("/api/geo-status")
def status():
    return JSONResponse(document("coverage_audit.json"))


@router.get("/api/regions")
def regions(query: str=Query("",max_length=100), parent: str|None=None, level: str|None=None,
            offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200)):
    if level and level not in {"province","city","district"}: raise HTTPException(422,"无效行政层级")
    if parent and parent!="100000": region(parent)
    terms=search_text(query).strip().split()
    def matches(item):
        text=search_text(" ".join([item["id"],item.get("code") or "",item["full_name"],*(item.get("aliases") or [])]))
        return (not parent or item["parent"]==parent) and (not level or item["level"]==level) and all(t in text for t in terms)
    selected=[i for i in catalog_index().values() if matches(i)]
    selected.sort(key=lambda i:(0 if query.strip() in (i["id"],i["name"]) else 1,i["full_name"],i["id"]))
    return {"items":[compact(i) for i in selected[offset:offset+limit]],"count":len(selected),"offset":offset,"limit":limit,"version":document("admin_catalog.json")["version"]}


@router.get("/api/regions/{region_id}")
def region_detail(region_id: str):
    return region(region_id)


@router.get("/api/regions/{region_id}/geometry")
def region_geometry(region_id: str):
    item=region(region_id)
    if item["geometry_status"]!="available":
        return JSONResponse({"region":item,"geometry":None,"status":"missing","locate_parent":item["parent"]})
    for feature in document(f"{item['level']}.json")["features"]:
        if feature["properties"]["id"]==region_id: return JSONResponse(feature)
    # Never silently substitute a parent outline for a missing county.
    raise HTTPException(503,"目录与边界文件不一致，请重新运行边界审计")
