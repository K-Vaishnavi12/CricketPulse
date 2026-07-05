"""Text-to-SQL agent using Gemini + LangChain over the DuckDB warehouse.

Users ask questions in English; the agent:
    1. sends the question + schema summary to Gemini
    2. Gemini returns a DuckDB SQL query
    3. we execute it (read-only), return results
    4. Gemini rewrites the results in plain English
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage

from src.common.logging import get_logger
from src.genai.llm import get_llm
from src.warehouse.db import get_conn

log = get_logger("genai.sql")


SCHEMA_HINT = """
You are querying a DuckDB warehouse for a live IPL cricket analytics platform.
Use ONLY the tables/columns below. DuckDB SQL syntax. Return a SINGLE SELECT.
Never modify data. No comments, no explanations - only the SQL.

TABLES:

bronze.balls_raw (ball-by-ball events, one row per delivery)
    match_id                VARCHAR
    innings                 INTEGER   -- 1 or 2
    over                    INTEGER   -- 0..19
    ball                    INTEGER   -- 1..6 (or more with wides/no-balls)
    batting_team            VARCHAR
    bowling_team            VARCHAR
    batter                  VARCHAR
    non_striker             VARCHAR
    bowler                  VARCHAR
    runs_batter             INTEGER   -- runs off the bat
    runs_extras             INTEGER   -- wides/no-balls/byes
    extras_kind             VARCHAR   -- 'wide' | 'no ball' | 'bye' | 'leg bye' | NULL
    is_wicket               BOOLEAN
    dismissal_kind          VARCHAR   -- 'bowled' | 'caught' | 'lbw' | 'run out' | ...
    player_out              VARCHAR
    innings_score           INTEGER   -- team score AFTER this ball
    innings_wickets         INTEGER
    innings_overs_completed DOUBLE
    target                  INTEGER   -- non-NULL in innings 2
    event_ts                TIMESTAMP

bronze.matches_raw
    match_id, team_a, team_b, venue,
    toss_winner, toss_decision, start_ts,
    winner, result_text, end_ts

bronze.predictions_raw (real-time ML predictions per ball)
    match_id, innings, over, ball,
    win_prob_team_a, win_prob_team_b,
    predicted_final_score, event_ts

silver.fact_balls (cleaned balls with `phase` = 'powerplay'|'middle'|'death'
                   plus `is_boundary`, `is_dot`, `runs_total`)

gold.batter_scorecard  (match_id, innings, batter, runs, balls_faced,
                        fours, sixes, strike_rate, is_out, dismissal)
gold.bowler_scorecard  (match_id, innings, bowler, overs, runs_conceded,
                        wickets, economy, dot_balls)
gold.innings_summary   (match_id, innings, batting_team, bowling_team,
                        total_runs, total_wickets, overs, run_rate,
                        boundary_count, dot_ball_pct)
gold.over_progression  (match_id, innings, over, runs_in_over, wickets_in_over,
                        cumulative_score, cumulative_wickets, phase)

analytics.match_summary (match_id, team_a, team_b, venue, winner,
                         inn1_score, inn1_wickets, inn2_score, inn2_wickets,
                         total_balls, total_boundaries, last_updated)

RULES:
- If the user says "current match", "this match", or "the live match",
  use the match_id with the latest event_ts in bronze.balls_raw.
- Always LIMIT to 50 rows unless the user asks for more.
- Never SELECT *; always list the needed columns.
- Prefer the `gold` and `analytics` tables for aggregated questions.
""".strip()


ANSWER_PROMPT = """
You are a friendly cricket analyst. A user asked a question about a live match.
Below is the SQL query you generated and the results table (as CSV).

Explain the answer in 1-3 short sentences of natural English.
- Do NOT restate the SQL.
- If the result is empty, say the data isn't available yet.
- Use cricket lingo (over, wicket, strike rate) but keep it simple.

USER QUESTION:
{question}

SQL:
{sql}

RESULTS (CSV):
{results_csv}
""".strip()


_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_sql(text: str) -> str:
    m = _SQL_FENCE.search(text)
    if m:
        return m.group(1).strip().rstrip(";")
    # fall back: take first SELECT statement in the reply
    text = text.strip().rstrip(";")
    idx = text.upper().find("SELECT")
    if idx >= 0:
        return text[idx:].strip()
    return text.strip()


def _is_safe_select(sql: str) -> bool:
    s = sql.strip().lower()
    if not s.startswith(("select", "with")):
        return False
    banned = ("insert ", "update ", "delete ", "drop ", "alter ",
              "create ", "attach ", "copy ", "pragma ", "call ")
    return not any(b in s for b in banned)


@dataclass
class SQLAnswer:
    question: str
    sql: str
    results: pd.DataFrame
    natural_answer: str
    error: Optional[str] = None


def ask(question: str) -> SQLAnswer:
    """Full round-trip: NL question -> SQL -> results -> NL answer."""
    llm = get_llm(temperature=0.0)

    # 1. NL -> SQL
    sql_reply = llm.invoke([
        SystemMessage(content=SCHEMA_HINT),
        HumanMessage(content=f"Question: {question}\n\nReturn only the DuckDB SQL query."),
    ]).content
    sql = _extract_sql(sql_reply)
    log.info(f"Generated SQL: {sql}")

    if not _is_safe_select(sql):
        return SQLAnswer(
            question=question,
            sql=sql,
            results=pd.DataFrame(),
            natural_answer=("I can only run read-only SELECT queries. "
                            "The generated query was blocked for safety."),
            error="unsafe_sql",
        )

    # 2. Execute
    try:
        with get_conn(read_only=True) as conn:
            results = conn.execute(sql).df()
    except Exception as e:
        log.error(f"SQL execution failed: {e}")
        return SQLAnswer(
            question=question,
            sql=sql,
            results=pd.DataFrame(),
            natural_answer=f"Sorry, I couldn't run that query. ({e})",
            error=str(e),
        )

    # 3. Results -> NL
    csv_snippet = results.head(20).to_csv(index=False) if not results.empty else "(no rows)"
    nl_llm = get_llm(temperature=0.4)
    nl_reply = nl_llm.invoke([
        HumanMessage(content=ANSWER_PROMPT.format(
            question=question, sql=sql, results_csv=csv_snippet,
        )),
    ]).content

    return SQLAnswer(
        question=question,
        sql=sql,
        results=results,
        natural_answer=nl_reply.strip(),
    )
