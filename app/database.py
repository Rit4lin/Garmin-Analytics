from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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
    from app.models import all_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
