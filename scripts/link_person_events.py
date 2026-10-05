import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
events=json.loads((ROOT/'data/events.json').read_text(encoding='utf8'))
path=ROOT/'data/history/journeys.json'; journeys=json.loads(path.read_text(encoding='utf8'))
for person in journeys.values():
    for node in person.get('nodes',[]):
        matches=[e['id'] for e in events if person['name'] in e.get('people',[]) and int(e.get('year',0))==int(node.get('year',0))]
        node['event_ids']=matches[:12]
    person['event_count']=sum(len(n.get('event_ids',[])) for n in person.get('nodes',[]))
path.write_text(json.dumps(journeys,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print({p['name']:sum(bool(n.get('event_ids')) for n in p['nodes']) for p in journeys.values()})
