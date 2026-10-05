from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.history import read

client=TestClient(app)


@pytest.mark.parametrize('year',range(1921,1951))
def test_all_historical_years_have_own_assessment_and_explicit_precision(year):
    response=client.get(f'/api/history/{year}')
    assert response.status_code==200
    data=response.json()
    assert data['year']==year and data['snapshot_date']==f'{year}-12-31'
    assert data['display_mode']=='historical' and data['summary']
    assert data['coverage_status']=='source_coverage'
    assert data['sources']
    assert all(a['geometry_status']=='source_location_envelope' and a['source_ids'] for a in data['territories'])
    assert all(int(b['start_date'][:4])<=year<=int(b['end_date'][:4]) for b in data['battles'])


@pytest.mark.parametrize('year',[1951,1978,date.today().year])
def test_modern_year_has_battle_layers_and_no_historical_territory(year):
    data=client.get(f'/api/history/{year}').json()
    assert data['display_mode']=='modern'
    assert not data['territories']
    assert isinstance(data['battles'], list)


@pytest.mark.parametrize('year',[1920,date.today().year+1])
def test_invalid_year(year):
    assert client.get(f'/api/history/{year}').status_code==422


def test_bounds_filter_does_not_remove_annual_battle_index():
    full=client.get('/api/history/1937').json()
    local=client.get('/api/history/1937?bbox=112,25,116,31').json()
    assert len(local['territories'])<len(full['territories'])
    assert local['battles']==full['battles']
    assert client.get('/api/history/1937?bbox=nan,0,1,2').status_code==422


def test_postwar_no_japanese_control_and_early_party_not_a_territory():
    for year in [1945,1949,1950]:
        assert not any(r['faction']=='japan' for r in client.get(f'/api/history/{year}').json()['territories'])
    assert not any(r['faction']=='ccp' for r in client.get('/api/history/1921').json()['territories'])


def test_cross_year_campaigns_and_routes():
    for key in ['huaihai','pingjin']:
        assert key in {b['id'] for b in client.get('/api/history/1948').json()['battles']}
        assert key in {b['id'] for b in client.get('/api/history/1949').json()['battles']}
        detail=client.get(f'/api/battles/{key}').json()
        assert detail['sources'] and len(detail['stages'])>=3
        assert all(r['start_year']==r['end_year'] for r in detail['routes'])
    assert client.get('/api/battles/missing').status_code==404


def test_catalog_and_sources_resolve():
    catalog=client.get('/api/history-catalog').json()
    assert catalog['battle_count']==len(read('battles.json'))
    assert len(catalog['battle_checklist'])==catalog['battle_count']
    assert len(catalog['phases'])==5
    assert catalog['open_items']
    sources=read('sources.json')
    for battle in read('battles.json'):
        assert set(battle['source_ids'])<=sources.keys()
        assert battle['start_date']<=battle['end_date']
        for route in battle['routes']:
            assert all(-180<=p[0]<=180 and -90<=p[1]<=90 for p in route['coordinates'])


@pytest.mark.parametrize('person_id',list(read('journeys.json')))
def test_ten_people_own_visits_not_all_related_events(person_id):
    data=client.get(f'/api/persons/{person_id}/timeline').json()
    nodes=data['nodes']; by_id={n['id']:n for n in nodes}
    assert len(nodes)>=10
    assert nodes[0]['stage']=='birth' and nodes[-1]['stage']=='death'
    assert data['sources']
    assert [n['year'] for n in nodes]==sorted(n['year'] for n in nodes)
    for segment in data['segments']:
        start,end=by_id[segment['from']],by_id[segment['to']]
        assert start['domestic'] and end['domestic'] and start['route_eligible'] and end['route_eligible']
        assert nodes.index(end)==nodes.index(start)+1  # Never bridge an overseas gap.
        assert segment['coordinates']==[start['coords'],end['coords']]
        assert start['coords']!=end['coords']
        assert start['year'] not in data['ambiguous_years']
        assert end['year'] not in data['ambiguous_years']


def test_corrected_person_locations():
    journeys=read('journeys.json')
    assert next(n for n in journeys['liu_shaoqi']['nodes'] if n['stage']=='death')['location']=='开封'
    assert any(n['year']==1922 and n['location']=='柏林' for n in journeys['zhu_de']['nodes'])
    assert any(n['year']==1926 and n['location']=='莫斯科' for n in journeys['deng_xiaoping']['nodes'])
    assert not any(n['year']==1949 and n['location']=='北京' for n in journeys['deng_xiaoping']['nodes'])
    assert client.get('/api/persons/not-found/timeline').status_code==404


def test_region_year_filter_compatible():
    events=client.get('/api/events').json()['items']
    event=next(e for e in events if e['year']>=1921)
    full=client.get(f"/api/regions/{event['province']}/stories").json()
    subset=client.get(f"/api/regions/{event['province']}/stories?year={event['year']}").json()
    assert full['count']>=subset['count']>0
    assert all(e['year']==event['year'] for e in subset['items'])
