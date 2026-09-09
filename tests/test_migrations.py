from sqlalchemy import create_engine, inspect, text

from app import database
from app.config import Settings


def test_existing_database_is_adopted_and_migrated(tmp_path, monkeypatch) -> None:
    path = tmp_path / "legacy.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE activities (activity_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(
            text("CREATE TABLE sync_state (name VARCHAR(40) PRIMARY KEY, status VARCHAR(30))")
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "get_settings", lambda: Settings(database_url=url))
    database.init_database()
    columns = {column["name"] for column in inspect(engine).get_columns("sync_state")}
    assert {"backfill_status", "backfill_cursor_date", "retry_count"}.issubset(columns)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0002_sync_backfill_state"
        )
