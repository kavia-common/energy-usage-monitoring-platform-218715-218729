from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, Optional, Sequence

import psycopg2
import psycopg2.extras

from src.api.settings import settings


def _build_dsn() -> str:
    """
    Build a PostgreSQL DSN from available env vars.

    Prefer POSTGRES_URL when provided (it may already include user/password/host/port/db).
    Fallback to individual pieces if needed.
    """
    if settings.postgres_url:
        return settings.postgres_url

    # Fallback: only used if POSTGRES_URL isn't provided by runtime.
    # NOTE: If this fallback is reached, ensure orchestrator sets POSTGRES_* env vars properly.
    user = settings.postgres_user or ""
    password = settings.postgres_password or ""
    host = settings.postgres_host or "localhost"
    port = settings.postgres_port or "5432"
    db = settings.postgres_db or ""
    auth = f"{user}:{password}@" if user or password else ""
    return f"postgresql://{auth}{host}:{port}/{db}"


@contextmanager
def get_conn() -> Iterator[psycopg2.extensions.connection]:
    """Yield a Postgres connection with DictCursor; commits on success, rollbacks on failure."""
    conn = psycopg2.connect(_build_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(sql: str, params: Sequence[Any] | None = None) -> Optional[Dict[str, Any]]:
    """Fetch a single row as dict, or None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(sql: str, params: Sequence[Any] | None = None) -> list[Dict[str, Any]]:
    """Fetch all rows as list of dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]


def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    """Execute a statement and return affected rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.rowcount


def execute_returning(sql: str, params: Sequence[Any] | None = None) -> Optional[Dict[str, Any]]:
    """Execute a statement with RETURNING and return the returned row."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            row = cur.fetchone()
            return dict(row) if row else None


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> int:
    """Execute many rows with execute_batch; returns total rows attempted."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)
            return cur.rowcount
