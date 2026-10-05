from pathlib import Path
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.military import load

client = TestClient(app)

def test_central_soviet_does_not_include_hunan_homonym():
    response = client.get('/api/control?year=1933').json()
    soviet = [f for f in response['features'] if f['id'].startswith('central-soviet-named-counties:')]
    assert len(soviet) == 19
    assert all(f['properties']['admin_id'][:2] in {'35', '36'} for f in soviet)
    assert all(f['geometry']['type'] in {'Polygon', 'MultiPolygon'} for f in response['features'])

@pytest.mark.parametrize('bbox', ['nan,0,120,30', '0,0,inf,50', '-190,0,150,90', '10,30,9,40'])
def test_invalid_control_bbox(bbox):
    assert client.get('/api/control', params={'bbox': bbox}).status_code == 422

def test_units_filter_battle_and_category():
    battle = client.get('/api/units?year=1948&battle_id=huaihai').json()['units']
    assert len(battle) == 4
    assert not client.get('/api/units?year=1948&category=long_march').json()['units']
    assert not client.get('/api/units?year=1935&battle_id=huaihai').json()['units']

def test_month_record_does_not_arrive_on_first_day_or_claim_stay():
    early = client.get('/api/units/red2/timeline?at=1936-06-15').json()
    assert all(w['location'] != '甘孜' for w in early['arrivals'])
    assert early['position'] is None
    late = client.get('/api/units/red2/timeline?at=1936-06-30T23:59:59.999999').json()
    assert late['last_arrival']['location'] == '甘孜'
    assert not late['interpolate']

def test_archived_military_sources_and_waypoint_references():
    root = Path(__file__).resolve().parents[1]
    sources = load('data/history/military-sources.json')
    for unit in load('data/history/unit-movements.json')['units']:
        for node in unit['waypoints']:
            assert set(node['source_ids']) <= set(sources)
    for source in sources.values():
        if source.get('archive_path'):
            assert hashlib.sha256((root/source['archive_path']).read_bytes()).hexdigest() == source['sha256']

def test_historical_record_dates_and_pre_1921_sources():
    records = load('data/history/control-records.json')['records']
    mainland = next(item for item in records if item['id'] == 'mainland-prc')
    assert mainland['start_at'] == '1949-10-01'
    han = next(item for item in records if item['id'] == 'wuhan-occupied-core')
    south = next(item for item in records if item['id'] == 'wuhan-occupied-south-bank')
    assert han['start_at'] == '1938-10-25' and han['admin_ids'] == ['420102', '420103', '420104']
    assert south['start_at'] == '1938-10-27' and south['admin_ids'] == ['420105', '420106']
    root = Path(__file__).resolve().parents[1]
    events = json.loads((root/'data/events.json').read_text(encoding='utf-8'))
    for event in events:
        if event.get('year', 9999) < 1921:
            assert not set(event.get('source_ids', [])) & {'chronicle', 'postwar_official'}
