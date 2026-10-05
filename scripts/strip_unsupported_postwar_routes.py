"""Remove invented polylines where the cited record only identifies a theatre."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "data" / "history" / "battles_post1949.json"
items = json.loads(path.read_text(encoding="utf-8"))
for item in items:
    for route in item.get("routes", []):
        route.pop("segments", None)
    if item.get("routes"):
        item["route_note"] = "来源只给出战区或方向，地图不连接为逐段行军线。"
    item["routes"] = []
    item["route_playback"] = False
    for force in item.get("forces", []):
        if isinstance(force.get("strength"), str) and ("公开报道" in force["strength"] or force["strength"] == "来源条目"):
            force["strength"] = None
            force["strength_precision"] = "not_published"
    if item.get("id") == "joint_sword_2024b":
        item["precision_note"] = "国防部公开报道给出演习日期、军种与活动区域；未公布逐舰逐机轨迹。"
        item["route_note"] = "活动区域以事件点和战区信息展示，不绘制轨迹。"
path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"updated {len(items)} post-1949 records")
