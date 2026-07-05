-- CricketPulse warehouse schema (medallion: bronze -> silver -> gold)

-- ============================================================================
-- BRONZE: raw events exactly as they land from Kafka
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.balls_raw (
    ingest_ts               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    match_id                VARCHAR   NOT NULL,
    innings                 INTEGER   NOT NULL,
    over                    INTEGER   NOT NULL,
    ball                    INTEGER   NOT NULL,
    batting_team            VARCHAR   NOT NULL,
    bowling_team            VARCHAR   NOT NULL,
    batter                  VARCHAR   NOT NULL,
    non_striker             VARCHAR   NOT NULL,
    bowler                  VARCHAR   NOT NULL,
    runs_batter             INTEGER   NOT NULL,
    runs_extras             INTEGER   NOT NULL,
    extras_kind             VARCHAR,
    is_wicket               BOOLEAN   NOT NULL,
    dismissal_kind          VARCHAR,
    player_out              VARCHAR,
    innings_score           INTEGER   NOT NULL,
    innings_wickets         INTEGER   NOT NULL,
    innings_overs_completed DOUBLE    NOT NULL,
    target                  INTEGER,
    event_ts                TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.matches_raw (
    ingest_ts     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    match_id      VARCHAR PRIMARY KEY,
    team_a        VARCHAR NOT NULL,
    team_b        VARCHAR NOT NULL,
    venue         VARCHAR NOT NULL,
    toss_winner   VARCHAR NOT NULL,
    toss_decision VARCHAR NOT NULL,
    start_ts      TIMESTAMP NOT NULL,
    winner        VARCHAR,
    result_text   VARCHAR,
    end_ts        TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.predictions_raw (
    ingest_ts               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    match_id                VARCHAR NOT NULL,
    innings                 INTEGER NOT NULL,
    over                    INTEGER NOT NULL,
    ball                    INTEGER NOT NULL,
    win_prob_team_a         DOUBLE  NOT NULL,
    win_prob_team_b         DOUBLE  NOT NULL,
    predicted_final_score   INTEGER,
    event_ts                TIMESTAMP NOT NULL
);

-- ============================================================================
-- SILVER: cleaned, enriched, ready-for-analytics
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS silver;

-- rebuilt every ETL run
CREATE TABLE IF NOT EXISTS silver.fact_balls (
    match_id                VARCHAR,
    innings                 INTEGER,
    over                    INTEGER,
    ball                    INTEGER,
    phase                   VARCHAR,        -- powerplay / middle / death
    batting_team            VARCHAR,
    bowling_team            VARCHAR,
    batter                  VARCHAR,
    bowler                  VARCHAR,
    runs_batter             INTEGER,
    runs_extras             INTEGER,
    runs_total              INTEGER,
    is_wicket               BOOLEAN,
    dismissal_kind          VARCHAR,
    player_out              VARCHAR,
    innings_score           INTEGER,
    innings_wickets         INTEGER,
    innings_overs_completed DOUBLE,
    target                  INTEGER,
    is_boundary             BOOLEAN,        -- 4 or 6 off the bat
    is_dot                  BOOLEAN,        -- 0 total runs
    event_ts                TIMESTAMP
);

-- ============================================================================
-- GOLD: business-ready aggregates for the dashboard + GenAI SQL
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.batter_scorecard (
    match_id      VARCHAR,
    innings       INTEGER,
    batter        VARCHAR,
    runs          INTEGER,
    balls_faced   INTEGER,
    fours         INTEGER,
    sixes         INTEGER,
    strike_rate   DOUBLE,
    is_out        BOOLEAN,
    dismissal     VARCHAR
);

CREATE TABLE IF NOT EXISTS gold.bowler_scorecard (
    match_id      VARCHAR,
    innings       INTEGER,
    bowler        VARCHAR,
    overs         DOUBLE,
    runs_conceded INTEGER,
    wickets       INTEGER,
    economy       DOUBLE,
    dot_balls     INTEGER
);

CREATE TABLE IF NOT EXISTS gold.innings_summary (
    match_id        VARCHAR,
    innings         INTEGER,
    batting_team    VARCHAR,
    bowling_team    VARCHAR,
    total_runs      INTEGER,
    total_wickets   INTEGER,
    overs           DOUBLE,
    run_rate        DOUBLE,
    boundary_count  INTEGER,
    dot_ball_pct    DOUBLE
);

CREATE TABLE IF NOT EXISTS gold.over_progression (
    match_id     VARCHAR,
    innings      INTEGER,
    over         INTEGER,
    runs_in_over INTEGER,
    wickets_in_over INTEGER,
    cumulative_score INTEGER,
    cumulative_wickets INTEGER,
    phase        VARCHAR
);
