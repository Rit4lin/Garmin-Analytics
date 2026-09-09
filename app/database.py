from collections.abc import Generator

from alembic.config import Config
from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from alembic import command
from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine():
    from sqlalchemy import create_engine

    engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
    return engine


engine: Engine = _engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_database() -> None:
    """Aplica migraciones y adopta sin pérdida las DB de la versión create_all."""
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    tables = set(inspect(engine).get_table_names())
    # La primera versión publicada creaba tablas directamente y no tenía revisión.
    # Se marca como 0001 para que la migración incremental siguiente sea segura.
    if "alembic_version" not in tables and {"sync_state", "activities"}.issubset(tables):
        command.stamp(config, "0001_initial")
    command.upgrade(config, "head")


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
