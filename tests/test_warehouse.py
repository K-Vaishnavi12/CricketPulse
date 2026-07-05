"""Tests for the warehouse layer."""
import tempfile
from pathlib import Path

import duckdb

from src.warehouse.db import SCHEMA_FILE, TRANSFORM_FILE


def _fresh_db():
    tmp = Path(tempfile.mkdtemp()) / "test.duckdb"
    conn = duckdb.connect(str(tmp))
    return tmp, conn


def test_schema_creates_all_tables():
    _, conn = _fresh_db()
    try:
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        tables = conn.execute("""
            SELECT table_schema||'.'||table_name AS tbl
            FROM information_schema.tables
            WHERE table_schema IN ('bronze','silver','gold')
            ORDER BY tbl
        """).fetchall()
        names = {t[0] for t in tables}
        expected = {
            "bronze.balls_raw",
            "bronze.matches_raw",
            "bronze.predictions_raw",
            "silver.fact_balls",
            "gold.batter_scorecard",
            "gold.bowler_scorecard",
            "gold.innings_summary",
            "gold.over_progression",
        }
        assert expected.issubset(names), f"Missing: {expected - names}"
    finally:
        conn.close()


def test_transformations_run_on_empty_bronze():
    _, conn = _fresh_db()
    try:
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        # should not raise even with no data
        conn.execute(TRANSFORM_FILE.read_text(encoding="utf-8"))
        n = conn.execute("SELECT COUNT(*) FROM silver.fact_balls").fetchone()[0]
        assert n == 0
    finally:
        conn.close()
