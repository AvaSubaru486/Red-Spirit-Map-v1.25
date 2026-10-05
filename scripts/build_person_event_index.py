"""Add an auditable event index to the public people catalogue."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
people_path = ROOT / "data/persons.json"
people = json.loads(people_path.read_text(encoding="utf-8"))
for person in people:
    name = person.get("name", "")
    ids = [event["id"] for event in events if name and name in event.get("people", [])]
    person["event_ids"] = ids
    person["event_count"] = len(ids)
people_path.write_text(json.dumps(people, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print({"people": len(people), "minimum_event_count": min((p["event_count"] for p in people), default=0)})
