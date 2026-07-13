"""Sesión y engine SQLAlchemy."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from opciones.modules.configuration import get_settings


def create_db_engine(url: str | None = None, *, echo: bool = False):
    settings = get_settings()
    return create_engine(url or settings.database_url, echo=echo, future=True)


def create_session_factory(engine=None) -> sessionmaker[Session]:
    eng = engine or create_db_engine()
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)


def get_session(factory: sessionmaker[Session] | None = None) -> Generator[Session, None, None]:
    SessionLocal = factory or create_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
