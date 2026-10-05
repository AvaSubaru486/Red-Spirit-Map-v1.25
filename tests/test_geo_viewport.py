"""Viewport culling must improve speed WITHOUT removing source geography."""
import math

import pytest
from fastapi.testclient import TestClient

from app.main import app, bounds_intersect, geometry_features, display_geometry_features

client = TestClient(app)


def test_index_includes_names_and_parents_without_heavy_polygons():
    result = client.get("/api/geo-index").json()
    assert len(result["province"]) == 34
    assert len(result["city"]) == len(geometry_features("city"))
    assert any(row["id"] == "440000" and row["name"] == "广东省" for row in result["province"])
    for rows in result.values():
        for row in rows:
            assert "geometry" not in row
            if row["geometry_status"] == "available":
                assert len(row["bbox"]) == 4
            else:
                assert row["geometry_status"] == "missing"
                assert row["bbox"] is None


@pytest.mark.parametrize("level", ["province", "city", "district", "south_china_sea"])
def test_world_view_keeps_every_source_feature(level):
    original = display_geometry_features(level)
    response = client.get(f"/api/geo/{level}?bbox=-180,-90,180,90")
    assert response.status_code == 200
    assert {f["properties"]["id"] for f in response.json()["features"]} == {f["properties"]["id"] for f in original}
    assert response.json()["canonical_count"] == len(geometry_features(level))
    for feature in original:
        assert all(math.isfinite(value) for value in feature["bbox"])


@pytest.mark.parametrize("bounds", [
    [112.8, 22.7, 113.8, 23.6], [115.7, 39.4, 117.0, 40.5],
    [120, 21.8, 122.3, 25.5], [73, 35, 96, 49], [105, 3, 122, 23],
])
def test_viewport_matches_every_intersecting_district_including_islands(bounds):
    original = display_geometry_features("district")
    result = client.get("/api/geo/district", params={"bbox": ",".join(map(str, bounds))}).json()
    expected = {f["properties"]["id"] for f in original if bounds_intersect(f["bbox"], bounds)}
    assert {f["properties"]["id"] for f in result["features"]} == expected
    assert len(result["features"]) < len(original)
    assert result["source_count"] == len(original)


@pytest.mark.parametrize("bbox", ["1,2,3", "nan,1,2,3", "0,0,inf,1", "181,0,190,2", "5,0,1,2", "0,-91,1,0", "a,b,c,d"])
def test_invalid_viewport_is_rejected(bbox):
    assert client.get("/api/geo/district", params={"bbox": bbox}).status_code == 422


def test_empty_view_is_an_empty_collection_not_an_error():
    response = client.get("/api/geo/district?bbox=-50,-50,-49,-49")
    assert response.status_code == 200
    assert response.json()["features"] == []


def test_terminal_city_keeps_its_true_identity_at_district_zoom():
    result = client.get("/api/geo/district?bbox=113,22,114,24").json()
    feature = next(f for f in result["features"] if f["properties"]["id"] == "442000")
    assert feature["properties"]["level"] == "city"
    assert feature["properties"]["coverage_status"] == "no_county_level_units"
    assert feature["properties"]["display_role"] == "terminal_city"
    assert feature["properties"].get("coverage") != "city_fallback"
