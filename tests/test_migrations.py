import json

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
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
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "get_settings", lambda: Settings(database_url=url))
    database.init_database()
    columns = {column["name"] for column in inspect(engine).get_columns("sync_state")}
    tables = set(inspect(engine).get_table_names())
    assert {"backfill_status", "backfill_cursor_date", "retry_count"}.issubset(columns)
    assert {"performance_metrics", "personal_records"}.issubset(tables)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0004_performance_analytics_v2"
        )


def test_nested_training_metrics_are_backfilled_from_raw_status(tmp_path) -> None:
    path = tmp_path / "training.db"
    url = f"sqlite:///{path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0002_sync_backfill_state")

    payload = {
        "status": {
            "mostRecentVO2Max": {"generic": {"vo2MaxValue": 48.0}},
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {
                    "primary-device": {
                        "primaryTrainingDevice": True,
                        "trainingStatusFeedbackPhrase": "RECOVERY_1",
                        "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 191},
                    }
                }
            },
        }
    }
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO training_metrics (metric_date, raw_json) VALUES (:date, :raw_json)"),
            {"date": "2026-01-04", "raw_json": json.dumps(payload)},
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT vo2max, training_load, acute_load, training_status "
                "FROM training_metrics WHERE metric_date = '2026-01-04'"
            )
        ).one()
    assert row == (48.0, 191, 191, "RECOVERY_1")
