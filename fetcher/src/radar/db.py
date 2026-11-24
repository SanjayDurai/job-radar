"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from radar.settings import database_url


@lru_cache
def engine() -> Engine:
    # pool_pre_ping: Neon suspends idle computes, so stale connections are common
    return create_engine(database_url(), pool_pre_ping=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = sessionmaker(bind=engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
