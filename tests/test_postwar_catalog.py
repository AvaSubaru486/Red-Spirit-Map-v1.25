import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_postwar_battles_and_modern_drill_are_listed():
    items = client.get('/api/battles?year=1951').json()['items']
    assert items
    assert all('forces' in item and 'commanders' in item for item in items)
    drill = client.get('/api/battles?year=2024').json()['items']
    assert [item['id'] for item in drill] == ['joint_sword_2024b']


def test_theatre_records_do_not_expose_invented_route_segments():
    data = json.loads((Path(__file__).parents[1] / 'data/history/battles_post1949.json').read_text(encoding='utf-8'))
    assert all(not item.get('routes') and item.get('route_playback') is False for item in data)
    assert all('segments' not in route for item in data for route in item.get('routes', []))


def test_people_have_auditable_event_index():
    people = json.loads((Path(__file__).parents[1] / 'data/persons.json').read_text(encoding='utf-8'))
    assert len(people) >= 20
    assert min(person['event_count'] for person in people) >= 10
    assert all(len(person['event_ids']) == person['event_count'] for person in people)
