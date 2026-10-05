"""Use linked biographical observations for their corresponding event sources."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'data/events.json'
events = json.loads(path.read_text(encoding='utf-8'))
journeys = json.loads((ROOT / 'data/history/journeys.json').read_text(encoding='utf-8'))
by_id = {event['id']: event for event in events}
changed = 0
for journey in journeys.values():
    for node in journey.get('nodes', []):
        for event_id in node.get('event_ids', []):
            event = by_id.get(event_id)
            if not event or not event_id.startswith('p_') or event.get('year') != node.get('year'):
                continue
            if event.get('people') != [journey['name']]:
                continue
            sources = node.get('source_ids', [])
            if not sources:
                continue
            event['source_ids'] = sources
            if event.get('year', 9999) < 1921:
                event['source_ids'] = [source for source in sources if source not in {'chronicle', 'postwar_official'}]
            event['source_locator'] = f"{journey['name']}生平：{node['title']}（{node.get('date') or node['year']}）"
            if node.get('date'):
                event['date'] = node['date']
                event['date_precision'] = node.get('date_precision', 'day')
            if node.get('stage') == 'birth':
                event['categories'] = ['sites_people']
                event['category'] = 'sites_people'
                event['themes'] = ['sites_people']
            changed += 1
by_title = {
    '鲁迅故里': ('鲁迅', ['lu']),
    '朱德故居': ('朱德', ['zhu2']),
    '毛泽东故居': ('毛泽东', ['mao1']),
    '周恩来故居': ('周恩来', ['zhou']),
    '邓小平故里': ('邓小平', ['deng']),
}
for event in events:
    mapping = by_title.get(event.get('title'))
    if mapping and event.get('year', 9999) < 1921:
        event['people'] = [mapping[0]]
        event['source_ids'] = mapping[1]
        event['source_locator'] = f"{mapping[0]}生平或故居资料"
        changed += 1
path.write_text(json.dumps(events, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print({'linked_biographical_events_updated': changed})
