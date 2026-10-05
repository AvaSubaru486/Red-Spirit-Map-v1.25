"""Remove numeric-looking battle fields that lack field-level source support."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for filename in ('battles.json', 'battles_post1949.json'):
    path = ROOT / 'data/history' / filename
    items = json.loads(path.read_text(encoding='utf-8'))
    for item in items:
        if item.get('id') == 'joint_sword_2024b':
            item['kind'] = 'military_exercise'
            item['category'] = 'military_action'
        if item.get('commanders') == '来源条目':
            item['commanders'] = None
        for force in item.get('forces', []):
            if force.get('strength') is not None:
                force['strength'] = None
                force['strength_precision'] = 'not_published'
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('cleared unsupported strength and commander placeholders')
