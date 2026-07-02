"""SQLAlchemy engine / session / declarative base (P2).

The control plane uses synchronous SQLAlchemy 2.0 + psycopg3. The DSN is built
from the same Settings used by the app, so migrations and the running service
agree on the target database.
"""
from __future__ import annotations

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


def get_engine(s: Settings | None = None) -> Engine:
    s = s or get_settings()
    return create_engine(build_dsn(s), pool_pre_ping=True, future=True)


def get_sessionmaker(s: Settings | None = None) -> sessionmaker:
    return sessionmaker(bind=get_engine(s), expire_on_commit=False, future=True)
