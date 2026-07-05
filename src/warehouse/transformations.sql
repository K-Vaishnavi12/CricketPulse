-- CricketPulse: bronze -> silver -> gold transformations
-- Run periodically by the Airflow DAG (or synchronously by the consumer)

-- ---------------------------------------------------------------------------
-- SILVER: cleaned, enriched fact table
-- ---------------------------------------------------------------------------
DELETE FROM silver.fact_balls;

INSERT INTO silver.fact_balls
SELECT
    match_id,
    innings,
    over,
    ball,
    CASE
        WHEN over < 6  THEN 'powerplay'
        WHEN over < 15 THEN 'middle'
        ELSE                'death'
    END                                     AS phase,
    batting_team,
    bowling_team,
    batter,
    bowler,
    runs_batter,
    runs_extras,
    (runs_batter + runs_extras)             AS runs_total,
    is_wicket,
    dismissal_kind,
    player_out,
    innings_score,
    innings_wickets,
    innings_overs_completed,
    target,
    (runs_batter IN (4, 6))                 AS is_boundary,
    ((runs_batter + runs_extras) = 0)       AS is_dot,
    event_ts
FROM bronze.balls_raw;

-- ---------------------------------------------------------------------------
-- GOLD: batter scorecard
-- ---------------------------------------------------------------------------
DELETE FROM gold.batter_scorecard;

INSERT INTO gold.batter_scorecard
SELECT
    match_id,
    innings,
    batter,
    SUM(runs_batter)                        AS runs,
    SUM(CASE WHEN extras_kind IN ('wide') THEN 0 ELSE 1 END) AS balls_faced,
    SUM(CASE WHEN runs_batter = 4 THEN 1 ELSE 0 END) AS fours,
    SUM(CASE WHEN runs_batter = 6 THEN 1 ELSE 0 END) AS sixes,
    ROUND(
        CASE
            WHEN SUM(CASE WHEN extras_kind IN ('wide') THEN 0 ELSE 1 END) = 0 THEN 0
            ELSE SUM(runs_batter) * 100.0
                 / SUM(CASE WHEN extras_kind IN ('wide') THEN 0 ELSE 1 END)
        END, 2)                             AS strike_rate,
    MAX(CASE WHEN player_out = batter THEN TRUE ELSE FALSE END) AS is_out,
    ANY_VALUE(CASE WHEN player_out = batter THEN dismissal_kind END) AS dismissal
FROM bronze.balls_raw
GROUP BY match_id, innings, batter;

-- ---------------------------------------------------------------------------
-- GOLD: bowler scorecard
-- ---------------------------------------------------------------------------
DELETE FROM gold.bowler_scorecard;

INSERT INTO gold.bowler_scorecard
SELECT
    match_id,
    innings,
    bowler,
    ROUND(
        (SUM(CASE WHEN extras_kind IN ('wide', 'no ball') THEN 0 ELSE 1 END) / 6.0),
        1)                                                          AS overs,
    SUM(runs_batter + runs_extras)                                  AS runs_conceded,
    SUM(CASE WHEN is_wicket
                  AND dismissal_kind NOT IN ('run out')
             THEN 1 ELSE 0 END)                                     AS wickets,
    ROUND(
        CASE
            WHEN SUM(CASE WHEN extras_kind IN ('wide', 'no ball') THEN 0 ELSE 1 END) = 0
                 THEN 0
            ELSE SUM(runs_batter + runs_extras) * 6.0
                 / SUM(CASE WHEN extras_kind IN ('wide', 'no ball') THEN 0 ELSE 1 END)
        END, 2)                                                     AS economy,
    SUM(CASE WHEN (runs_batter + runs_extras) = 0 THEN 1 ELSE 0 END) AS dot_balls
FROM bronze.balls_raw
GROUP BY match_id, innings, bowler;

-- ---------------------------------------------------------------------------
-- GOLD: innings summary
-- ---------------------------------------------------------------------------
DELETE FROM gold.innings_summary;

INSERT INTO gold.innings_summary
SELECT
    match_id,
    innings,
    ANY_VALUE(batting_team)                                          AS batting_team,
    ANY_VALUE(bowling_team)                                          AS bowling_team,
    MAX(innings_score)                                               AS total_runs,
    MAX(innings_wickets)                                             AS total_wickets,
    MAX(innings_overs_completed)                                     AS overs,
    ROUND(
        MAX(innings_score) / NULLIF(MAX(innings_overs_completed), 0),
        2)                                                           AS run_rate,
    SUM(CASE WHEN runs_batter IN (4, 6) THEN 1 ELSE 0 END)            AS boundary_count,
    ROUND(
        100.0 * SUM(CASE WHEN (runs_batter + runs_extras) = 0 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        2)                                                           AS dot_ball_pct
FROM bronze.balls_raw
GROUP BY match_id, innings;

-- ---------------------------------------------------------------------------
-- GOLD: over-by-over progression
-- ---------------------------------------------------------------------------
DELETE FROM gold.over_progression;

INSERT INTO gold.over_progression
WITH per_over AS (
    SELECT
        match_id,
        innings,
        over,
        SUM(runs_batter + runs_extras)                        AS runs_in_over,
        SUM(CASE WHEN is_wicket THEN 1 ELSE 0 END)            AS wickets_in_over
    FROM bronze.balls_raw
    GROUP BY match_id, innings, over
)
SELECT
    match_id,
    innings,
    over,
    runs_in_over,
    wickets_in_over,
    SUM(runs_in_over)   OVER (PARTITION BY match_id, innings ORDER BY over) AS cumulative_score,
    SUM(wickets_in_over) OVER (PARTITION BY match_id, innings ORDER BY over) AS cumulative_wickets,
    CASE
        WHEN over < 6  THEN 'powerplay'
        WHEN over < 15 THEN 'middle'
        ELSE                'death'
    END                                                                     AS phase
FROM per_over;
