"""DuckDB connection helpers + schema bootstrap."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from src.common.config import settings

SCHEMA_FILE = Path(__file__).parent / "schema.sql"
TRANSFORM_FILE = Path(__file__).parent / "transformations.sql"


@contextmanager
def get_conn(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a DuckDB connection to the warehouse."""
    conn = duckdb.connect(str(settings.duckdb_absolute_path), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    """Create bronze/silver/gold schemas + tables. Idempotent."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql)


def run_transformations() -> None:
    """Rebuild silver + gold tables from bronze."""
    sql = TRANSFORM_FILE.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql)
