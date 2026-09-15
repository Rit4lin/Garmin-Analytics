import tomllib
from pathlib import Path

from fastapi.testclient import TestClient
from garminconnect import GarminConnectConnectionError

from app.config import Settings
from app.main import app
from app.services.garmin_client import GarminClient, GarminTokenError


def test_healthz_and_docs_work() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        assert client.get("/api/summary?days=0").status_code == 422


def test_release_version_is_consistent() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    assert project["version"] == app.version == "2.0.0"


def test_dashboard_surfaces_v2_release_metrics() -> None:
    with TestClient(app) as client:
        javascript = client.get("/static/dashboard.js").text
    assert "fitness_age" in javascript
    assert "recovery-components" in javascript
    assert "aerobic_te" in javascript
    assert "anaerobic_te" in javascript


def test_missing_tokens_do_not_break_web() -> None:
    with TestClient(app) as client:
        assert client.get("/").status_code == 200


def test_missing_tokens_have_clear_error(tmp_path) -> None:
    client = GarminClient(Settings(garmin_tokens=str(tmp_path / "missing")))
    try:
        client.connect()
    except GarminTokenError as exc:
        assert "garmin-mcp-auth" in str(exc)
    else:
        raise AssertionError("Se esperaba GarminTokenError")


def test_garmin_connection_error_is_not_a_token_error(tmp_path, monkeypatch) -> None:
    class OfflineGarmin:
        def __init__(self, **_kwargs):
            pass

        def login(self, _token_dir):
            raise GarminConnectConnectionError("offline")

    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    (token_dir / "garmin_tokens.json").write_text("{}")
    monkeypatch.setattr("app.services.garmin_client.Garmin", OfflineGarmin)
    client = GarminClient(Settings(garmin_tokens=str(token_dir)))
    try:
        client.connect()
    except GarminConnectConnectionError:
        pass
    else:
        raise AssertionError("Una caída de Garmin no puede convertirse en error de token")


def test_sync_endpoint_reports_cooldown_without_forcing(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.api.sync_service.request_sync", lambda: False)
    monkeypatch.setattr(
        "app.routers.api.sync_service.status",
        lambda: {"cooldown_seconds": 42},
    )
    with TestClient(app) as client:
        response = client.post("/api/sync")
    assert response.status_code == 202
    assert response.json()["cooldown_seconds"] == 42
