"""Non-mutating unit coverage for the local deployment bootstrap."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import pytest

if sys.platform != "win32":
    pytest.skip("The EXE bootstrap targets Windows.", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "自动部署" / "deploy.py"
if not DEPLOYMENT.exists():
    pytest.skip("v1.15 Pages special edition does not publish the EXE bootstrap.", allow_module_level=True)
spec = importlib.util.spec_from_file_location("deployment_bootstrap", DEPLOYMENT)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class FakeResponse:
    status = 200
    def __init__(self, identity, status="ok"):
        from io import BytesIO
        self.headers = {"X-Red-Map-Project": identity}
        self.content = BytesIO(json.dumps({"status": status}).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, *args):
        return self.content.read(*args)


def test_health_fingerprint_matches_real_app():
    from app.main import PROJECT_ID
    assert deploy.PROJECT_ID == PROJECT_ID
    assert deploy.PYTHON == ROOT / "runtime" / "python.exe"
    assert deploy.CACHE.is_relative_to(ROOT)


@pytest.mark.parametrize("identity,status,expected", [
    (deploy.PROJECT_ID, "ok", True),
    (None, "ok", False),
    ("different-project", "ok", False),
    (deploy.PROJECT_ID, "failed", False),
])
def test_service_identity_is_not_just_health_json(monkeypatch, identity, status, expected):
    monkeypatch.setattr(deploy, "request", lambda *args, **kwargs: FakeResponse(identity, status))
    assert deploy.is_our_server(8010) is expected


def test_connection_error_is_not_ready(monkeypatch):
    def offline(*args, **kwargs):
        raise ConnectionRefusedError("offline")
    monkeypatch.setattr(deploy, "request", offline)
    assert not deploy.is_our_server(8010)


def test_reuse_does_not_spawn_duplicate_process(monkeypatch):
    monkeypatch.setattr(deploy, "port_available", lambda port: port != 8012)
    monkeypatch.setattr(deploy, "is_our_server", lambda port: port == 8012)
    monkeypatch.setattr(deploy, "verify_site", lambda port: None)
    def unexpected_spawn(*args, **kwargs):
        pytest.fail("A running instance should not cause another server process")
    monkeypatch.setattr(deploy.subprocess, "Popen", unexpected_spawn)
    assert deploy.choose_and_start(8010, {}) == {"port": 8012, "reused": True}


def test_occupied_port_range_does_not_kill_or_spawn(monkeypatch):
    monkeypatch.setattr(deploy, "port_available", lambda port: False)
    monkeypatch.setattr(deploy, "is_our_server", lambda port: False)
    with pytest.raises(RuntimeError, match="端口"):
        deploy.choose_and_start(8010, {})
