"""SQLAlchemy engine / session / declarative base (P2).

The control plane uses synchronous SQLAlchemy 2.0 + psycopg3. The DSN is built
from the same Settings used by the app, so migrations and the running service
agree on the target database.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def build_dsn(s: Settings) -> str:
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"
    )


@lru_cache(maxsize=4)
def _engine_for_dsn(dsn: str) -> Engine:
    return create_engine(dsn, pool_pre_ping=True, pool_size=5, max_overflow=10, future=True)


def get_engine(s: Settings | None = None) -> Engine:
    """Process-wide engine per DSN — one pool, not one per caller."""
    s = s or get_settings()
    return _engine_for_dsn(build_dsn(s))


def get_sessionmaker(s: Settings | None = None) -> sessionmaker:
    return sessionmaker(bind=get_engine(s), expire_on_commit=False, future=True)
