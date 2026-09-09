from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services.garmin_client import GarminClient, GarminTokenError


def test_healthz_and_docs_work() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        assert client.get("/api/summary?days=0").status_code == 422


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
