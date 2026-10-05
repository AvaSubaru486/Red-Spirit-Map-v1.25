"""Drop zero-length map segments while retaining their dated nodes."""
from __future__ import annotations
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'data/history/journeys.json'
data = json.loads(path.read_text(encoding='utf-8'))
for person in data.values():
    nodes = {node['id']: node for node in person.get('nodes', [])}
    person['segments'] = [segment for segment in person.get('segments', [])
                          if nodes.get(segment.get('from'), {}).get('coords') != nodes.get(segment.get('to'), {}).get('coords')]
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('journeys normalized')
