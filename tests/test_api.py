from fastapi.testclient import TestClient

from app.main import app, PROJECT_ID


client = TestClient(app)


def test_health_and_home_are_local() -> None:
    assert client.get("/api/health").json() == {"status": "ok", "mode": "offline"}
    assert client.get("/api/health").headers["X-Red-Map-Project"] == PROJECT_ID
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/vendor/leaflet.js" in response.text


def test_event_modes_filter_content() -> None:
    ordinary = client.get("/api/events").json()["items"]
    long_march = client.get("/api/events?mode=long_march").json()["items"]
    anti_japanese = client.get("/api/events?mode=anti_japanese").json()["items"]
    time_items = client.get("/api/events?mode=time&year=1935").json()["items"]
    assert len(ordinary) >= 100
    assert long_march
    assert anti_japanese
    assert all("long_march" in item["themes"] for item in long_march)
    assert all("anti_japanese" in item["themes"] for item in anti_japanese)
    assert all(item["year"] == 1935 for item in time_items)


def test_geometry_levels_and_south_china_sea_are_local() -> None:
    province = client.get("/api/geo/province").json()
    city = client.get("/api/geo/city").json()
    district = client.get("/api/geo/district").json()
    sea = client.get("/api/geo/south_china_sea").json()
    assert len(province["features"]) >= 34
    assert len(city["features"]) >= 300
    assert len(district["features"]) >= 2500
    assert sea["features"]
    assert any(feature["properties"]["name"] == "台湾省" for feature in province["features"])
    assert sum(feature["properties"].get("parent") == "710000" for feature in city["features"]) >= 22
    index = client.get("/api/geo-index").json()
    catalog = {row["id"]: row for rows in index.values() for row in rows}
    for feature in city["features"] + district["features"]:
        row = catalog[feature["properties"]["id"]]
        assert feature["properties"]["level"] == row["level"]
        assert row["parent"] == "100000" or row["parent"] in catalog
        assert feature["properties"].get("coverage") != "city_fallback"
    visible = {f["properties"]["id"] for f in district["features"]}
    for row in index["city"]:
        if row["coverage_status"] == "no_county_level_units":
            assert row["id"] in visible and row["child_count"] == 0
        else:
            assert any(child["parent"] == row["id"] for child in index["district"])
    assert all(feature.get("geometry", {}).get("coordinates") for feature in province["features"] + city["features"] + district["features"])


def test_detail_and_region_story_endpoints() -> None:
    item = client.get("/api/events").json()["items"][0]
    detail = client.get(f"/api/events/{item['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == item["title"]
    stories = client.get(f"/api/regions/{item['province']}/stories")
    assert stories.status_code == 200
    assert stories.json()["count"] >= 1


def test_person_mode_and_routes() -> None:
    person = client.get("/api/persons").json()["items"][0]
    response = client.get(f"/api/events?mode=person&person={person['name']}")
    assert response.status_code == 200
    assert all(person["name"] in item["people"] for item in response.json()["items"])
    assert client.get("/api/routes/long_march").json()["routes"]


def test_sun_yat_sen_former_residence_is_available() -> None:
    items = client.get("/api/events").json()["items"]
    residence = next(item for item in items if item["id"] == "s054_sun_yat_sen_former_residence")
    assert residence["kind"] == "residence"
    assert "孙中山" in residence["people"]


def test_person_timelines_cover_all_people() -> None:
    people = client.get("/api/persons").json()["items"]
    assert len(people) >= 20
    all_events = client.get("/api/events").json()["items"]
    for person in people:
        timeline = [item for item in all_events if person["name"] in item.get("people", [])]
        assert len(timeline) >= 10
        assert any("出生" in item.get("tags", []) for item in timeline)
        assert any("逝世" in item.get("tags", []) for item in timeline)
