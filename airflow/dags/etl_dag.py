"""CricketPulse Airflow DAG: bronze -> silver -> gold ETL every minute + hourly rollups.

The DAG runs inside the Airflow container. The DuckDB file is mounted at
/opt/airflow/data/warehouse/cricketpulse.duckdb (see docker-compose.yml).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from airflow import DAG
from airflow.operators.python import PythonOperator


DUCKDB_PATH = "/opt/airflow/data/warehouse/cricketpulse.duckdb"
SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.match_summary (
    match_id       VARCHAR PRIMARY KEY,
    team_a         VARCHAR,
    team_b         VARCHAR,
    venue          VARCHAR,
    winner         VARCHAR,
    inn1_score     INTEGER,
    inn1_wickets   INTEGER,
    inn2_score     INTEGER,
    inn2_wickets   INTEGER,
    total_balls    INTEGER,
    total_boundaries INTEGER,
    last_updated   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_warehouse_exists() -> None:
    """Guard: if the DuckDB file hasn't been created yet, skip cleanly."""
    p = Path(DUCKDB_PATH)
    if not p.exists():
        raise FileNotFoundError(
            f"DuckDB file not found at {DUCKDB_PATH}. "
            "Run `python scripts/bootstrap.py` on the host first."
        )


def run_silver_gold() -> None:
    _ensure_warehouse_exists()
    conn = duckdb.connect(DUCKDB_PATH)
    try:
        conn.execute(SCHEMA_SQL)

        # We embed the transformations here (mirror of src/warehouse/transformations.sql)
        # so the DAG is self-contained and independent of host code.
        conn.execute(_TRANSFORMATIONS_SQL)
    finally:
        conn.close()


def refresh_match_summary() -> None:
    _ensure_warehouse_exists()
    conn = duckdb.connect(DUCKDB_PATH)
    try:
        conn.execute("""
            DELETE FROM analytics.match_summary;

            INSERT INTO analytics.match_summary
            WITH inn AS (
                SELECT match_id, innings,
                       MAX(innings_score) AS score,
                       MAX(innings_wickets) AS wickets
                FROM bronze.balls_raw
                GROUP BY match_id, innings
            ),
            per_match AS (
                SELECT match_id,
                       COUNT(*) AS total_balls,
                       SUM(CASE WHEN runs_batter IN (4,6) THEN 1 ELSE 0 END) AS total_boundaries
                FROM bronze.balls_raw
                GROUP BY match_id
            )
            SELECT
                m.match_id,
                m.team_a,
                m.team_b,
                m.venue,
                m.winner,
                COALESCE(MAX(CASE WHEN inn.innings=1 THEN inn.score END), 0)   AS inn1_score,
                COALESCE(MAX(CASE WHEN inn.innings=1 THEN inn.wickets END), 0) AS inn1_wickets,
                COALESCE(MAX(CASE WHEN inn.innings=2 THEN inn.score END), 0)   AS inn2_score,
                COALESCE(MAX(CASE WHEN inn.innings=2 THEN inn.wickets END), 0) AS inn2_wickets,
                COALESCE(pm.total_balls, 0)      AS total_balls,
                COALESCE(pm.total_boundaries, 0) AS total_boundaries,
                CURRENT_TIMESTAMP                AS last_updated
            FROM bronze.matches_raw m
            LEFT JOIN inn      ON inn.match_id = m.match_id
            LEFT JOIN per_match pm ON pm.match_id = m.match_id
            GROUP BY m.match_id, m.team_a, m.team_b, m.venue, m.winner,
                     pm.total_balls, pm.total_boundaries;
        """)
    finally:
        conn.close()


_TRANSFORMATIONS_SQL = """
-- silver.fact_balls (rebuild)
CREATE TABLE IF NOT EXISTS silver.fact_balls (
    match_id VARCHAR, innings INTEGER, over INTEGER, ball INTEGER, phase VARCHAR,
    batting_team VARCHAR, bowling_team VARCHAR, batter VARCHAR, bowler VARCHAR,
    runs_batter INTEGER, runs_extras INTEGER, runs_total INTEGER,
    is_wicket BOOLEAN, dismissal_kind VARCHAR, player_out VARCHAR,
    innings_score INTEGER, innings_wickets INTEGER, innings_overs_completed DOUBLE,
    target INTEGER, is_boundary BOOLEAN, is_dot BOOLEAN, event_ts TIMESTAMP
);
DELETE FROM silver.fact_balls;
INSERT INTO silver.fact_balls
SELECT match_id, innings, over, ball,
       CASE WHEN over<6 THEN 'powerplay' WHEN over<15 THEN 'middle' ELSE 'death' END,
       batting_team, bowling_team, batter, bowler,
       runs_batter, runs_extras, runs_batter+runs_extras,
       is_wicket, dismissal_kind, player_out,
       innings_score, innings_wickets, innings_overs_completed,
       target, runs_batter IN (4,6), (runs_batter+runs_extras)=0, event_ts
FROM bronze.balls_raw;

-- gold.innings_summary (rebuild)
CREATE TABLE IF NOT EXISTS gold.innings_summary (
    match_id VARCHAR, innings INTEGER, batting_team VARCHAR, bowling_team VARCHAR,
    total_runs INTEGER, total_wickets INTEGER, overs DOUBLE, run_rate DOUBLE,
    boundary_count INTEGER, dot_ball_pct DOUBLE
);
DELETE FROM gold.innings_summary;
INSERT INTO gold.innings_summary
SELECT match_id, innings,
       ANY_VALUE(batting_team), ANY_VALUE(bowling_team),
       MAX(innings_score), MAX(innings_wickets),
       MAX(innings_overs_completed),
       ROUND(MAX(innings_score)/NULLIF(MAX(innings_overs_completed),0), 2),
       SUM(CASE WHEN runs_batter IN (4,6) THEN 1 ELSE 0 END),
       ROUND(100.0*SUM(CASE WHEN (runs_batter+runs_extras)=0 THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0), 2)
FROM bronze.balls_raw GROUP BY match_id, innings;
"""


default_args = {
    "owner": "cricketpulse",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(seconds=30),
}


with DAG(
    dag_id="cricketpulse_etl",
    description="Rebuild silver + gold + analytics from bronze events",
    default_args=default_args,
    schedule="* * * * *",   # every minute (real-time-ish)
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["cricketpulse", "etl"],
    max_active_runs=1,
) as dag:

    silver_gold = PythonOperator(
        task_id="rebuild_silver_gold",
        python_callable=run_silver_gold,
    )

    match_summary = PythonOperator(
        task_id="refresh_match_summary",
        python_callable=refresh_match_summary,
    )

    silver_gold >> match_summary
