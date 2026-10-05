"""Audit the actual snapshot honestly; unknown official coverage is not success."""
import hashlib
import json
from collections import Counter
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.admin import document, catalog_index
from app.main import app, geometry_features, display_geometry_features
from scripts.audit_admin_bundle import audit

client = TestClient(app)


def test_snapshot_has_no_orphans_duplicates_or_fake_counties():
    index = catalog_index()
    reference = document("admin_reference.json")["items"]
    assert len(index) == len(reference) == len(document("admin_catalog.json")["items"])
    assert set(index) == {row["id"] for row in reference}
    counts = Counter(row["parent"] for row in index.values())
    available = set()
    for level in ("province", "city", "district"):
        for feature in geometry_features(level):
            p = feature["properties"]
            assert p["level"] == level
            assert p["id"] not in available
            assert "_city_coverage" not in p["id"]
            assert p.get("coverage") != "city_fallback"
            assert feature["geometry"]["coordinates"]
            available.add(p["id"])
    for identifier, row in index.items():
        assert row["parent"] == "100000" or row["parent"] in index
        assert row["child_count"] == counts[identifier]
        assert (identifier in available) == (row["geometry_status"] == "available")
        path = [index[key]["name"] for key in row["ancestor_ids"]] + [row["name"]]
        assert row["full_name"] == " · ".join(path)


def test_audit_does_not_disguise_known_gaps_or_unverified_official_version():
    report = audit()
    assert report["structural_valid"]
    assert not report["complete"]
    assert not report["official_current_verified"]
    assert not report["snapshot_complete"]
    assert {item["name"] for item in report["missing_geometry"]} == {"和安县", "和康县"}
    for field in ("duplicate_ids", "duplicate_codes", "duplicate_reference_ids", "orphan_parents", "empty_geometry", "invalid_geometry", "hash_mismatches", "geometry_property_errors", "reference_mismatches"):
        assert report[field] == []


@pytest.mark.parametrize("parent,count", [
    ("110000", 16), ("120000", 16), ("310000", 16), ("500000", 37),
    ("810000", 18), ("820000", 8), ("710000", 22),
])
def test_special_region_snapshot_children(parent, count):
    result = client.get("/api/regions", params={"parent": parent, "limit": 200}).json()
    assert result["count"] == len(result["items"]) == count
    assert all(item["parent"] == parent and item["geometry_status"] == "available" for item in result["items"])


def test_taiwan_townships_and_corrected_provincial_counties():
    index = catalog_index()
    towns = [i for i in index.values() if i["id"].startswith("tw:") and i["level"] == "district"]
    assert len(towns) == 368
    assert all(index[t["parent"]]["parent"] == "710000" for t in towns)
    for identifier, province in (("419001", "410000"), ("429004", "420000"), ("469001", "460000"), ("659011", "650000"), ("659012", "650000")):
        assert index[identifier]["level"] == "district"
        assert index[identifier]["parent"] == province
    assert "500157" in index
    assert "500105" not in index and "500112" not in index


def test_terminal_city_and_no_intermediate_municipality_are_not_counties():
    index = catalog_index()
    terminals = {i["id"] for i in index.values() if i["coverage_status"] == "no_county_level_units"}
    assert terminals == {"441900", "442000", "460400", "620200"}
    assert all(index[key]["child_count"] == 0 and index[key]["level"] == "city" for key in terminals)
    city_view = {f["properties"]["id"]: f["properties"] for f in display_geometry_features("city")}
    for identifier in ("110000", "120000", "310000", "500000", "810000", "820000"):
        assert city_view[identifier]["level"] == "province"
        assert city_view[identifier]["display_role"] == "direct_province"
    district_view = {f["properties"]["id"]: f["properties"] for f in display_geometry_features("district")}
    assert all(district_view[key]["level"] == "city" for key in terminals)


@pytest.mark.parametrize("query,expected", [("广东 中山", "442000"), ("110101", "110101"), ("台北 中正", "tw:63000050"), ("臺北市", "tw:63000")])
def test_directory_search_by_path_code_and_original_name(query, expected):
    data = client.get("/api/regions", params={"query": query, "limit": 200}).json()
    assert expected in {item["id"] for item in data["items"]}


def test_paging_geometry_lookup_and_missing_status():
    first = client.get("/api/regions?limit=25").json()
    second = client.get("/api/regions?limit=25&offset=25").json()
    assert first["count"] == len(catalog_index())
    assert not ({i["id"] for i in first["items"]} & {i["id"] for i in second["items"]})
    for identifier in ("440000", "442000", "110101", "469001", "659012", "tw:63000", "tw:63000050", "810001", "820001"):
        result = client.get(f"/api/regions/{identifier}/geometry")
        assert result.status_code == 200
        assert result.json()["properties"]["id"] == identifier
        assert result.json()["geometry"]["coordinates"]
    for identifier in ("pending:hean", "pending:hekang"):
        result = client.get(f"/api/regions/{identifier}/geometry").json()
        assert result["status"] == "missing" and result["geometry"] is None
        assert result["locate_parent"] == "653200"
    assert client.get("/api/regions/nonexistent/geometry").status_code == 404
    for params in ({"offset": -1}, {"limit": 201}, {"level": "village"}):
        assert client.get("/api/regions", params=params).status_code == 422


def test_corrupted_parent_and_geometry_cannot_pass_audit(tmp_path):
    # A tiny complete province/city/county subtree isolates validation from the
    # known missing counties, without copying the full nationwide dataset.
    keys = {"440000", "440100", "440103"}
    source_items = [deepcopy(catalog_index()[key]) for key in sorted(keys)]
    for item in source_items:
        item["child_count"] = sum(child["parent"] == item["id"] for child in source_items)
    manifest = deepcopy(document("admin_manifest.json"))
    manifest["official_current_verified"] = True
    for level in ("province", "city", "district"):
        features = [deepcopy(f) for f in geometry_features(level) if f["properties"]["id"] in keys]
        filename = f"{level}.json"
        raw = json.dumps({"features": features}, ensure_ascii=False).encode("utf-8")
        (tmp_path / filename).write_bytes(raw)
        manifest["files"][filename]["sha256"] = hashlib.sha256(raw).hexdigest()
    def save(name, data):
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    save("admin_manifest.json", manifest)
    save("admin_reference.json", {"items": source_items})
    catalog = {"version": "test", "items": source_items}
    save("admin_catalog.json", catalog)
    assert audit(tmp_path)["complete"]
    source_items[-1]["parent"] = "999999"
    save("admin_catalog.json", catalog)
    report = audit(tmp_path)
    assert not report["structural_valid"]
    assert report["orphan_parents"] and report["geometry_property_errors"]
