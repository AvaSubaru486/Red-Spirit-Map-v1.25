"""Add source-indexed battle fields and bind every person node to an event."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    history = ROOT / "data" / "history"
    battles_path = history / "battles.json"
    battles = json.loads(battles_path.read_text(encoding="utf-8"))
    for battle in battles:
        participants = battle.get("participants") or []
        faction = battle.get("faction") or ("ccp" if any("红军" in p or "解放军" in p for p in participants) else "other")
        branch = battle.get("branch") or "陆军"
        battle["faction"] = faction
        battle["branch"] = branch
        battle["commanders"] = battle.get("commanders") or "来源条目"
        battle["forces"] = battle.get("forces") or [
            {"name": name, "faction": faction, "branch": branch, "strength": "来源条目", "role": "参战方"}
            for name in participants
        ]
        for force in battle["forces"]:
            force.setdefault("faction", faction)
            force.setdefault("branch", branch)
            force.setdefault("strength", "来源条目")
            force.setdefault("role", "参战方")
    battles_path.write_text(json.dumps(battles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    events_path = ROOT / "data" / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    event_ids = {event["id"] for event in events}
    if "e2024_joint_sword_2024b" not in event_ids:
        events.append({
            "id": "e2024_joint_sword_2024b",
            "title": "联合利剑—2024B演习",
            "year": 2024,
            "date": "2024-10-14",
            "date_precision": "day",
            "period": "新时代",
            "province": "台湾海峡",
            "city": "台岛周边",
            "district": "台湾海峡及台岛北部南部以东",
            "location_precision": "theater",
            "kind": "battle",
            "themes": ["construction_reform"],
            "categories": ["construction_reform"],
            "category": "construction_reform",
            "people": [],
            "coords": [121.0, 24.2],
            "summary": "东部战区组织陆军、海军、空军、火箭军等兵力开展联合演习，演练海空战备警巡、要港要域封控、对海对陆打击和夺取综合制权。",
            "story": "国防部公开报道记录了演习日期、区域、参演军种和演练科目。",
            "tags": ["建国后", "军事行动", "联合演习"],
            "timeline_type": "milestone",
            "source_ids": ["official_2024_joint_sword"],
            "source_locator": "中华人民共和国国防部，东部战区开展联合利剑—2024B演习，2024-10-14",
        })
        event_ids.add("e2024_joint_sword_2024b")
    journeys_path = history / "journeys.json"
    journeys = json.loads(journeys_path.read_text(encoding="utf-8"))
    for person in journeys.values():
        for node in person.get("nodes", []):
            if not node.get("event_ids"):
                event_id = f"journey_{person['id']}_{node['id']}"
                if event_id not in event_ids:
                    event = {
                        "id": event_id,
                        "title": f"{person['name']}：{node['title']}",
                        "year": node["year"],
                        "date": node.get("date"),
                        "date_precision": node.get("date_precision", "year"),
                        "period": "人物生平时间线",
                        "province": node.get("location", "全国"),
                        "city": node.get("location", "全国"),
                        "district": node.get("location", "全国"),
                        "location_precision": node.get("coordinate_precision", "region"),
                        "kind": "person_event",
                        "themes": ["sites_people"],
                        "categories": ["sites_people"],
                        "category": "sites_people",
                        "people": [person["name"]],
                        "coords": node["coords"],
                        "summary": node["story"],
                        "story": node["story"],
                        "tags": ["人物线", "来源节点"],
                        "timeline_type": node.get("stage", "milestone"),
                        "source_ids": node.get("source_ids", ["chronicle"]),
                        "source_locator": f"{person['name']}生平节点：{node['title']}（{node['year']}）",
                    }
                    events.append(event)
                    event_ids.add(event_id)
                node["event_ids"] = [event_id]
            else:
                node["event_ids"] = list(dict.fromkeys(node["event_ids"]))
        person["event_count"] = sum(len(node.get("event_ids", [])) for node in person.get("nodes", []))
    events.sort(key=lambda event: (int(event.get("year", 0)), event.get("date") or "9999", event["id"]))
    events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    journeys_path.write_text(json.dumps(journeys, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog_path = history / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["event_count"] = len(events)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"events": len(events), "people": len(journeys), "min_person_events": min(p["event_count"] for p in journeys.values())})


if __name__ == "__main__":
    main()
