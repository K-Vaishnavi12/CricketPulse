"""CricketPulse Streamlit dashboard — Broadcast V2.

Run:
    streamlit run src/dashboard/app.py
"""
from __future__ import annotations

# --- make `src.` imports work regardless of how streamlit was launched ---
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# -------------------------------------------------------------------------

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.dashboard.live_sim import (
    is_live_active, live_status, start_new_match, step_live_match, stop_live_match,
)
from src.dashboard.theme import team_palette, team_short
from src.genai.commentator import explain_match_state
from src.genai.highlights import generate_highlights
from src.genai.llm import is_configured as genai_ready
from src.genai.sql_agent import ask
from src.warehouse.db import get_conn


# ============================================================================ #
# Page config
# ============================================================================ #
st.set_page_config(
    page_title="CricketPulse | Live Match Intelligence",
    page_icon="[C]",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================ #
# Data access helpers (all read-only, cached briefly)
# ============================================================================ #

@st.cache_data(ttl=3)
def _fetch_current_match() -> dict | None:
    with get_conn(read_only=True) as conn:
        row = conn.execute("""
            SELECT b.match_id, m.team_a, m.team_b, m.venue,
                   m.toss_winner, m.toss_decision, m.winner, m.result_text,
                   MAX(b.event_ts) AS last_ts
              FROM bronze.balls_raw b
              JOIN bronze.matches_raw m USING (match_id)
             GROUP BY b.match_id, m.team_a, m.team_b, m.venue,
                      m.toss_winner, m.toss_decision, m.winner, m.result_text
             ORDER BY last_ts DESC
             LIMIT 1
        """).fetchone()
    if row is None:
        return None
    keys = ["match_id", "team_a", "team_b", "venue", "toss_winner",
            "toss_decision", "winner", "result_text", "last_ts"]
    return dict(zip(keys, row))


@st.cache_data(ttl=3)
def _fetch_match_by_id(match_id: str) -> dict | None:
    with get_conn(read_only=True) as conn:
        row = conn.execute("""
            SELECT b.match_id, m.team_a, m.team_b, m.venue,
                   m.toss_winner, m.toss_decision, m.winner, m.result_text,
                   MAX(b.event_ts) AS last_ts
              FROM bronze.matches_raw m
              LEFT JOIN bronze.balls_raw b USING (match_id)
             WHERE m.match_id = ?
             GROUP BY b.match_id, m.team_a, m.team_b, m.venue,
                      m.toss_winner, m.toss_decision, m.winner, m.result_text
             LIMIT 1
        """, [match_id]).fetchone()
    if row is None:
        return None
    keys = ["match_id", "team_a", "team_b", "venue", "toss_winner",
            "toss_decision", "winner", "result_text", "last_ts"]
    return dict(zip(keys, row))


@st.cache_data(ttl=3)
def _fetch_live_score(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings,
                   ANY_VALUE(batting_team)          AS batting_team,
                   MAX(innings_score)               AS score,
                   MAX(innings_wickets)             AS wickets,
                   MAX(innings_overs_completed)     AS overs,
                   ANY_VALUE(target)                AS target
              FROM bronze.balls_raw
             WHERE match_id = ?
             GROUP BY innings ORDER BY innings
        """, [match_id]).df()


@st.cache_data(ttl=3)
def _fetch_win_prob(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, over, ball, win_prob_team_a, win_prob_team_b,
                   predicted_final_score, event_ts
              FROM bronze.predictions_raw
             WHERE match_id = ? ORDER BY event_ts
        """, [match_id]).df()


@st.cache_data(ttl=5)
def _fetch_batters(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, batter, runs, balls_faced, fours, sixes, strike_rate,
                   is_out, dismissal
              FROM gold.batter_scorecard
             WHERE match_id = ? AND balls_faced > 0
             ORDER BY innings, runs DESC
        """, [match_id]).df()


@st.cache_data(ttl=5)
def _fetch_bowlers(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, bowler, overs, runs_conceded, wickets, economy, dot_balls
              FROM gold.bowler_scorecard
             WHERE match_id = ?
             ORDER BY innings, wickets DESC, economy ASC
        """, [match_id]).df()


@st.cache_data(ttl=5)
def _fetch_over_progression(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, over, runs_in_over, wickets_in_over,
                   cumulative_score, phase
              FROM gold.over_progression
             WHERE match_id = ? ORDER BY innings, over
        """, [match_id]).df()


@st.cache_data(ttl=3)
def _fetch_recent_balls(match_id: str, n: int = 15) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, over, ball, batter, bowler,
                   runs_batter, runs_extras, extras_kind, is_wicket, dismissal_kind,
                   player_out, innings_score, innings_wickets, event_ts
              FROM bronze.balls_raw
             WHERE match_id = ?
             ORDER BY event_ts DESC LIMIT ?
        """, [match_id, n]).df()


@st.cache_data(ttl=3)
def _fetch_ticker_events(match_id: str, n: int = 20) -> pd.DataFrame:
    """Latest events summarized as short strings for the top ticker."""
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT over, ball, innings, batting_team, bowling_team, batter, bowler,
                   runs_batter, runs_extras, extras_kind, is_wicket, dismissal_kind,
                   player_out, innings_score, innings_wickets
              FROM bronze.balls_raw
             WHERE match_id = ? ORDER BY event_ts DESC LIMIT ?
        """, [match_id, n]).df()


@st.cache_data(ttl=3)
def _fetch_current_over_balls(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        latest = conn.execute("""
            SELECT innings, over FROM bronze.balls_raw
             WHERE match_id=? ORDER BY event_ts DESC LIMIT 1
        """, [match_id]).fetchone()
        if not latest:
            return pd.DataFrame()
        return conn.execute("""
            SELECT ball, runs_batter, runs_extras, extras_kind, is_wicket
              FROM bronze.balls_raw
             WHERE match_id=? AND innings=? AND over=? ORDER BY ball
        """, [match_id, latest[0], latest[1]]).df()


@st.cache_data(ttl=5)
def _fetch_momentum(match_id: str, overs_back: int = 3) -> dict:
    """Runs & wickets scored by each team in the LAST `overs_back` overs of ANY innings."""
    with get_conn(read_only=True) as conn:
        latest = conn.execute("""
            SELECT innings, over FROM bronze.balls_raw
             WHERE match_id=? ORDER BY event_ts DESC LIMIT 1
        """, [match_id]).fetchone()
        if not latest:
            return {}
        latest_inn, latest_over = int(latest[0]), int(latest[1])
        min_over = max(0, latest_over - overs_back + 1)
        rows = conn.execute("""
            SELECT batting_team,
                   SUM(runs_batter + runs_extras) AS runs,
                   SUM(CASE WHEN is_wicket THEN 1 ELSE 0 END) AS wickets
              FROM bronze.balls_raw
             WHERE match_id=? AND innings=? AND over >= ?
             GROUP BY batting_team
        """, [match_id, latest_inn, min_over]).df()
    if rows.empty:
        return {}
    return {row["batting_team"]: {"runs": int(row["runs"]), "wickets": int(row["wickets"])}
            for _, row in rows.iterrows()}


@st.cache_data(ttl=10)
def _fetch_all_matches() -> pd.DataFrame:
    """List every match ever recorded (for match history / picker)."""
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT m.match_id, m.team_a, m.team_b, m.venue,
                   m.winner, m.result_text, m.start_ts,
                   COALESCE(MAX(b.innings_score), 0) AS max_score,
                   COUNT(b.match_id) AS ball_count,
                   MAX(b.event_ts) AS last_ball_ts
              FROM bronze.matches_raw m
              LEFT JOIN bronze.balls_raw b ON b.match_id = m.match_id
             GROUP BY m.match_id, m.team_a, m.team_b, m.venue,
                      m.winner, m.result_text, m.start_ts
             ORDER BY COALESCE(MAX(b.event_ts), m.start_ts) DESC
             LIMIT 30
        """).df()


@st.cache_data(ttl=5)
def _fetch_match_kpis(match_id: str) -> dict:
    """Global counters for the sidebar KPI cards."""
    with get_conn(read_only=True) as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                                              AS balls,
                SUM(CASE WHEN runs_batter = 4 THEN 1 ELSE 0 END)     AS fours,
                SUM(CASE WHEN runs_batter = 6 THEN 1 ELSE 0 END)     AS sixes,
                SUM(CASE WHEN is_wicket THEN 1 ELSE 0 END)           AS wickets,
                SUM(runs_batter + runs_extras)                        AS runs,
                SUM(CASE WHEN (runs_batter + runs_extras) = 0 THEN 1 ELSE 0 END) AS dots
              FROM bronze.balls_raw WHERE match_id = ?
        """, [match_id]).fetchone()
    if row is None:
        return {"balls": 0, "fours": 0, "sixes": 0, "wickets": 0, "runs": 0, "dots": 0}
    return dict(zip(["balls", "fours", "sixes", "wickets", "runs", "dots"],
                    [int(v or 0) for v in row]))


@st.cache_data(ttl=5)
def _fetch_highlight_moments(match_id: str, limit: int = 8) -> pd.DataFrame:
    """Get most impactful ball events for the commentary/talks feed."""
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, over, ball, batter, bowler, batting_team,
                   runs_batter, runs_extras, extras_kind, is_wicket, dismissal_kind,
                   player_out, innings_score, innings_wickets, event_ts
              FROM bronze.balls_raw
             WHERE match_id=?
               AND (is_wicket = TRUE OR runs_batter = 6 OR runs_batter = 4)
             ORDER BY event_ts DESC
             LIMIT ?
        """, [match_id, limit]).df()


# ============================================================================ #
# Small helpers
# ============================================================================ #

def _chip_class(row: dict) -> tuple[str, str]:
    if row["is_wicket"]:
        return "chip-w", "W"
    if row["runs_batter"] == 6:
        return "chip-6", "6"
    if row["runs_batter"] == 4:
        return "chip-4", "4"
    if row["runs_extras"] > 0:
        kind = (row.get("extras_kind") or "x")[:2].upper()
        return "chip-x", f"+{kind}"
    if (row["runs_batter"] + row["runs_extras"]) == 0:
        return "chip-dot", "0"
    return f"chip-{row['runs_batter']}", str(row["runs_batter"])


def _ticker_snippet(row: dict) -> str:
    over = f"{int(row['over'])}.{int(row['ball'])}"
    team = team_short(row["batting_team"])
    score = f"{int(row['innings_score'])}/{int(row['innings_wickets'])}"
    if row["is_wicket"]:
        return f"<span class='tk-w'>W</span> OUT: {row.get('player_out') or row['batter']} · O{over} · {team} {score}"
    if row["runs_batter"] == 6:
        return f"<span class='tk-6'>SIX</span> {row['batter']} · O{over} · {team} {score}"
    if row["runs_batter"] == 4:
        return f"<span class='tk-4'>FOUR</span> {row['batter']} · O{over} · {team} {score}"
    if row["runs_batter"] > 0:
        return f"<span class='tk-r'>{row['runs_batter']}</span> {row['batter']} · O{over} · {team} {score}"
    if row["runs_extras"] > 0:
        return f"<span class='tk-x'>{(row.get('extras_kind') or 'extras')[:2].upper()}</span> · O{over} · {team} {score}"
    return f"<span class='tk-d'>0</span> · O{over} · {team} {score}"


# ============================================================================ #
# Full CSS (broadcast style)
# ============================================================================ #

def _inject_css(pal_a: dict, pal_b: dict) -> None:
    css = f"""
    <style>
    /* Hide Streamlit chrome */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    [data-testid="stAppViewContainer"] {{
        background:
          radial-gradient(1200px 500px at 0% 0%,  {pal_a['primary']}18 0%, transparent 55%),
          radial-gradient(1200px 500px at 100% 0%, {pal_b['primary']}18 0%, transparent 55%),
          radial-gradient(900px 500px at 50% 100%, #0e1a2e 0%, #060a14 60%),
          #05080e;
        color: #e8ecf3;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    section[data-testid="stSidebar"] {{ background: #060a14; border-right: 1px solid rgba(255,255,255,0.06); }}
    .block-container {{ padding-top: 1rem; max-width: 1400px; }}

    /* ---- Live ticker (ESPN style) ---- */
    .ticker-wrap {{
        position: relative;
        overflow: hidden;
        background: linear-gradient(90deg, #0a1424 0%, #0e1a2e 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }}
    .ticker-tag {{
        position: absolute;
        left: 0; top: 0; bottom: 0;
        z-index: 2;
        display: flex; align-items: center; padding: 0 18px;
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: #fff; font-weight: 800; font-size: 12px; letter-spacing: 1.5px;
        box-shadow: 4px 0 12px rgba(0,0,0,0.4);
    }}
    .ticker-tag::before {{
        content: '';
        display: inline-block;
        width: 8px; height: 8px; border-radius: 50%;
        background: #fff; margin-right: 8px;
        animation: pulse-dot 1.3s ease-in-out infinite;
    }}
    @keyframes pulse-dot {{
        0%,100% {{ opacity: 1; transform: scale(1); }}
        50% {{ opacity: 0.4; transform: scale(0.7); }}
    }}
    .ticker-scroll {{
        display: inline-block;
        white-space: nowrap;
        padding: 12px 24px 12px 110px;
        color: #cbd5e1; font-size: 14px;
        animation: scroll-left 45s linear infinite;
    }}
    .ticker-scroll span.sep {{ color: #475569; margin: 0 14px; }}
    .ticker-scroll .tk-w {{ background:#ef4444; color:#fff; padding:2px 8px; border-radius:4px; font-weight:800; font-size:11px; margin-right:6px; }}
    .ticker-scroll .tk-6 {{ background:#a855f7; color:#fff; padding:2px 8px; border-radius:4px; font-weight:800; font-size:11px; margin-right:6px; }}
    .ticker-scroll .tk-4 {{ background:#3b82f6; color:#fff; padding:2px 8px; border-radius:4px; font-weight:800; font-size:11px; margin-right:6px; }}
    .ticker-scroll .tk-r {{ background:#10b981; color:#fff; padding:2px 8px; border-radius:4px; font-weight:800; font-size:11px; margin-right:6px; }}
    .ticker-scroll .tk-x {{ background:#f59e0b; color:#1a1a1a; padding:2px 8px; border-radius:4px; font-weight:800; font-size:11px; margin-right:6px; }}
    .ticker-scroll .tk-d {{ background:#334155; color:#cbd5e1; padding:2px 8px; border-radius:4px; font-weight:700; font-size:11px; margin-right:6px; }}
    @keyframes scroll-left {{
        from {{ transform: translateX(0); }}
        to   {{ transform: translateX(-50%); }}
    }}

    /* ---- Hero ---- */
    .hero {{
        padding: 24px 28px;
        border-radius: 20px;
        background: linear-gradient(135deg, {pal_a['primary']}22 0%, {pal_b['primary']}22 100%);
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 22px;
        position: relative; overflow: hidden;
    }}
    .hero::before {{
        content: '';
        position: absolute;
        inset: 0;
        background:
            radial-gradient(400px 200px at 15% 40%, {pal_a['primary']}44 0%, transparent 60%),
            radial-gradient(400px 200px at 85% 60%, {pal_b['primary']}44 0%, transparent 60%);
        pointer-events: none;
    }}
    .hero-inner {{ position: relative; z-index: 1; }}
    .hero-title {{ font-size: 32px; font-weight: 800; color: #fff; letter-spacing: -0.6px; margin: 0; }}
    .hero-vs {{ color: #64748b; margin: 0 10px; font-weight: 500; }}
    .hero-sub {{ color: #94a3b8; font-size: 13px; margin-top: 6px; }}
    .live-pill, .finished-pill {{
        display: inline-flex; align-items:center;
        padding: 5px 14px;
        color: #fff; font-size: 11px; font-weight: 800;
        border-radius: 999px; letter-spacing: 1.2px;
        margin-right: 12px; vertical-align: middle;
    }}
    .live-pill {{
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        box-shadow: 0 0 20px rgba(239,68,68,0.5);
        animation: pulse 1.6s ease-in-out infinite;
    }}
    .live-pill::before {{
        content: ''; display:inline-block; width:6px; height:6px;
        border-radius:50%; background:#fff; margin-right:6px;
    }}
    .finished-pill {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); }}
    @keyframes pulse {{
        0%,100% {{ box-shadow: 0 0 20px rgba(239,68,68,0.5); }}
        50%     {{ box-shadow: 0 0 30px rgba(239,68,68,0.8); }}
    }}

    /* ---- Score cards ---- */
    .score-card {{
        border-radius: 20px; padding: 24px 26px;
        background: linear-gradient(160deg, #0d1729 0%, #0a1220 100%);
        border: 1px solid rgba(255,255,255,0.06);
        min-height: 170px; position: relative; overflow: hidden;
        transition: transform 0.2s;
    }}
    .score-card:hover {{ transform: translateY(-2px); }}
    .score-card.team-a {{ border-left: 4px solid {pal_a['primary']}; box-shadow: -4px 0 40px {pal_a['primary']}22; }}
    .score-card.team-b {{ border-left: 4px solid {pal_b['primary']}; box-shadow: -4px 0 40px {pal_b['primary']}22; }}
    .score-card.batting::after {{
        content: 'BATTING'; position: absolute; top: 18px; right: 20px;
        background: #ef4444; color: #fff; font-size: 10px; font-weight: 800;
        letter-spacing: 1.5px; padding: 4px 10px; border-radius: 999px;
        animation: pulse 1.6s ease-in-out infinite;
    }}
    .score-card .team-badge {{
        display: inline-block; padding: 4px 10px; border-radius: 6px;
        font-size: 11px; font-weight: 800; letter-spacing: 1.5px;
        color: #fff; margin-bottom: 8px;
    }}
    .score-card .team-name {{
        color: #cbd5e1; font-size: 14px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 4px;
    }}
    .score-card .score {{
        color: #fff; font-size: 52px; font-weight: 800;
        letter-spacing: -1.5px; line-height: 1;
    }}
    .score-card .score-sep {{ color: #475569; font-weight: 400; }}
    .score-card .score-sub {{ color: #94a3b8; font-size: 14px; margin-top: 6px; }}
    .score-card .chase-info {{
        color: #fbbf24; font-size: 13px; margin-top: 12px; font-weight: 600;
        padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.06);
    }}

    /* ---- Section titles ---- */
    .section-title {{
        color: #fff; font-size: 15px; font-weight: 700; margin: 26px 0 12px 0;
        text-transform: uppercase; letter-spacing: 1.5px;
        display: flex; align-items: center; gap: 10px;
    }}
    .section-title::before {{
        content: ''; display:inline-block;
        width: 3px; height: 18px;
        background: linear-gradient(180deg, {pal_a['primary']} 0%, {pal_b['primary']} 100%);
        border-radius: 2px;
    }}

    /* ---- Insight cards ---- */
    .insight-card {{
        padding: 18px 22px; border-radius: 16px;
        background: linear-gradient(135deg, rgba(139,92,246,0.10) 0%, rgba(59,130,246,0.10) 100%);
        border: 1px solid rgba(139,92,246,0.25);
        color: #e8ecf3; font-size: 15px; line-height: 1.55;
    }}
    .insight-card .badge {{
        display:inline-block; background:linear-gradient(135deg, #8b5cf6, #ec4899); color:#fff;
        padding:4px 10px; border-radius:6px; font-size:10px; font-weight:800;
        letter-spacing:1.2px; margin-right:10px; vertical-align:middle;
    }}
    .highlights-card {{
        padding: 20px 24px; border-radius: 16px;
        background: linear-gradient(135deg, rgba(251,191,36,0.10) 0%, rgba(239,68,68,0.08) 100%);
        border: 1px solid rgba(251,191,36,0.25);
        color: #f8fafc; font-size: 16px; line-height: 1.6;
        margin-bottom: 18px;
    }}
    .highlights-card .badge {{
        display:inline-block; background:linear-gradient(135deg, #fbbf24, #f59e0b); color:#1a1a1a;
        padding:4px 12px; border-radius:6px; font-size:10px; font-weight:800;
        letter-spacing:1.2px; margin-right:12px; vertical-align:middle;
    }}

    /* ---- Ball chips ---- */
    .ball-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0; }}
    .ball-chip {{
        display: inline-flex; align-items: center; justify-content: center;
        width: 42px; height: 42px; border-radius: 50%;
        font-weight: 800; font-size: 15px; color: #fff;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        transition: transform 0.2s;
    }}
    .ball-chip:hover {{ transform: scale(1.08); }}
    .chip-dot {{ background: #334155; }}
    .chip-1,.chip-2,.chip-3 {{ background: #475569; }}
    .chip-4 {{ background: linear-gradient(135deg, #3b82f6, #2563eb); box-shadow: 0 4px 16px rgba(59,130,246,0.5); }}
    .chip-6 {{ background: linear-gradient(135deg, #a855f7, #7c3aed); box-shadow: 0 4px 16px rgba(168,85,247,0.5); }}
    .chip-w {{ background: linear-gradient(135deg, #ef4444, #dc2626); box-shadow: 0 4px 16px rgba(239,68,68,0.5); }}
    .chip-x {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #1a1a1a; font-size: 12px; }}

    /* ---- Momentum bar ---- */
    .momentum-wrap {{
        background: #0a1220;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 18px 22px;
    }}
    .momentum-row {{ display:flex; align-items:center; margin-bottom: 12px; }}
    .momentum-row:last-child {{ margin-bottom: 0; }}
    .momentum-label {{ min-width: 90px; color: #cbd5e1; font-size: 13px; font-weight: 600; }}
    .momentum-bar-outer {{
        flex: 1; height: 26px; background: #0e1a2e;
        border-radius: 13px; overflow: hidden; margin: 0 12px;
        border: 1px solid rgba(255,255,255,0.04);
    }}
    .momentum-bar-inner {{
        height: 100%; display: flex; align-items: center;
        justify-content: flex-end; padding-right: 10px;
        color: #fff; font-weight: 800; font-size: 12px;
        transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .momentum-value {{ min-width: 90px; text-align: right; color: #fff; font-weight: 700; font-size: 13px; }}
    .momentum-value .wk {{ color: #ef4444; margin-left: 6px; }}

    /* ---- Ball feed lines ---- */
    .ball-line {{
        padding: 12px 16px; background: rgba(255,255,255,0.03);
        border-radius: 10px; margin-bottom: 6px;
        border-left: 3px solid #334155;
        font-size: 14px; color: #e8ecf3;
        display: flex; align-items: center; gap: 12px;
    }}
    .ball-line.wicket {{ border-left-color: #ef4444; background: rgba(239,68,68,0.06); }}
    .ball-line.six    {{ border-left-color: #a855f7; background: rgba(168,85,247,0.06); }}
    .ball-line.four   {{ border-left-color: #3b82f6; background: rgba(59,130,246,0.06); }}
    .ball-line .over-tag {{ color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 13px; min-width: 42px; }}
    .ball-line .msg {{ flex: 1; }}
    .ball-line .final-score {{ color: #94a3b8; font-weight: 700; }}

    /* ---- Player cards ---- */
    .player-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    @media (max-width: 900px) {{ .player-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .player-card {{
        background: linear-gradient(160deg, #0d1729 0%, #0a1220 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px; padding: 14px 16px;
        position: relative; overflow: hidden;
    }}
    .player-card.team-a-tint {{ border-top: 3px solid {pal_a['primary']}; }}
    .player-card.team-b-tint {{ border-top: 3px solid {pal_b['primary']}; }}
    .player-name {{ color: #fff; font-weight: 700; font-size: 15px; margin-bottom: 2px; }}
    .player-role {{ color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
    .player-stats {{ display: flex; justify-content: space-between; gap: 10px; margin-bottom: 8px; }}
    .stat-block .stat-value {{ color: #fff; font-size: 22px; font-weight: 800; line-height: 1; }}
    .stat-block .stat-label {{ color: #94a3b8; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }}
    .sr-bar {{
        height: 6px; background: #0e1a2e; border-radius: 3px; overflow: hidden;
    }}
    .sr-bar-fill {{
        height: 100%; background: linear-gradient(90deg, #10b981 0%, #fbbf24 60%, #ef4444 100%);
        border-radius: 3px;
    }}

    /* ---- Buttons / chat ---- */
    .stButton>button {{
        background: rgba(59,130,246,0.12); color: #93c5fd;
        border: 1px solid rgba(59,130,246,0.3);
        border-radius: 999px; padding: 6px 16px;
        font-size: 13px; font-weight: 500; transition: all 0.15s;
    }}
    .stButton>button:hover {{
        background: rgba(59,130,246,0.25);
        border-color: rgba(59,130,246,0.6); color: #fff;
    }}
    [data-testid="stDataFrame"] {{
        border-radius: 12px; overflow: hidden;
        border: 1px solid rgba(255,255,255,0.06);
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ============================================================================ #
# Sidebar — OTT navigation + controls
# ============================================================================ #

with st.sidebar:
    # Brand
    st.markdown("""
    <div style='padding: 4px 0 14px 0; border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 14px;'>
        <div style='font-size:22px; font-weight:800; letter-spacing:-0.5px; color:#fff;'>
            <span style='background:linear-gradient(135deg,#13a87c,#3b82f6);
                         -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                         background-clip:text;'>CricketPulse</span>
        </div>
        <div style='color:#64748b; font-size:11px; margin-top:2px; letter-spacing:1px; text-transform:uppercase;'>
            AI Match Intelligence
        </div>
    </div>
    """, unsafe_allow_html=True)

    # === Live Match Controls (compact) ===
    st.markdown("<div style='color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:1.2px; font-weight:700; margin-bottom:8px;'>Live Streaming</div>", unsafe_allow_html=True)
    if is_live_active():
        stat = live_status()
        st.success(f"● Streaming · {stat['balls_delivered']} balls")
        if st.button("Stop stream", use_container_width=True):
            stop_live_match()
            st.rerun()
    else:
        with st.expander("Start a new match", expanded=False):
            team_a_in = st.text_input("Team A", value="Mumbai Mavericks")
            team_b_in = st.text_input("Team B", value="Chennai Chargers")
            venue_in = st.text_input("Venue", value="Wankhede Stadium")
            if st.button("Start live match", type="primary", use_container_width=True):
                start_new_match(team_a_in, team_b_in, venue_in)
                st.session_state.selected_match_id = None
                st.rerun()

    st.divider()

    # === Match Picker (History) ===
    st.markdown("<div style='color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:1.2px; font-weight:700; margin-bottom:8px;'>Match History</div>", unsafe_allow_html=True)
    _all_matches = _fetch_all_matches()
    if _all_matches.empty:
        st.caption("No matches yet.")
    else:
        options = {"Live / Latest": None}
        for _, m in _all_matches.iterrows():
            label = f"{team_short(m['team_a'])} vs {team_short(m['team_b'])}"
            if m['result_text']:
                label += f" · {'W' if m['winner']==m['team_a'] else 'L'}"
            options[f"{label}  ({int(m['ball_count'])} balls)"] = m['match_id']
        selection = st.selectbox(
            "Select match", options.keys(),
            index=0,
            label_visibility="collapsed",
        )
        st.session_state.selected_match_id = options[selection]

    st.divider()

    # === Sidebar action selector (OTT-style) ===
    st.markdown("<div style='color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:1.2px; font-weight:700; margin-bottom:8px;'>Panels</div>", unsafe_allow_html=True)
    show_commentary_panel = st.toggle("Rich Commentary", value=True, help="AI-narrated key moments")
    show_stats_panel = st.toggle("Match Stats", value=True, help="Quick KPI counters")
    show_talks_panel = st.toggle("Talks & Chat", value=True, help="Ask the AI analyst")

    st.divider()

    # === Auto-refresh ===
    auto_refresh = st.toggle("Live auto-refresh (2s)", value=True)
    if auto_refresh:
        st_autorefresh(interval=2000, key="live_refresh")

    st.divider()

    # === Sidebar quick stats (shown after we know the match) ===
    # placeholder — filled after we compute the match below
    stats_placeholder = st.empty()

    # === Sidebar commentary preview (also filled below) ===
    commentary_placeholder = st.empty()

    st.divider()
    st.caption(
        "Kafka streaming · Airflow ETL · DuckDB warehouse · "
        "scikit-learn ML · LangChain + Gemini text-to-SQL"
    )


# Advance any live simulation before rendering
if is_live_active():
    step_live_match(balls_per_tick=3)


# ============================================================================ #
# MAIN
# ============================================================================ #

# Honor the sidebar match selector; otherwise fall back to the latest match.
_selected_id = st.session_state.get("selected_match_id")
match = _fetch_match_by_id(_selected_id) if _selected_id else _fetch_current_match()

if match is None:
    _inject_css({"primary": "#13a87c", "accent": "#22c9a0", "text_on": "#fff"},
                {"primary": "#3b82f6", "accent": "#60a5fa", "text_on": "#fff"})
    st.markdown("""
    <div class='hero'><div class='hero-inner'>
        <div class='hero-title'>CricketPulse</div>
        <div class='hero-sub'>Real-time cricket analytics + AI commentary. Start a match from the sidebar to see the dashboard come alive.</div>
    </div></div>
    """, unsafe_allow_html=True)
    st.info("Click **Start live match** in the sidebar to stream a fresh game.")
    st.stop()

pal_a = team_palette(match["team_a"])
pal_b = team_palette(match["team_b"])
_inject_css(pal_a, pal_b)


# ============================================================================ #
# Populate sidebar placeholders now that we know the match
# ============================================================================ #

if show_stats_panel:
    _kpis = _fetch_match_kpis(match["match_id"])
    with stats_placeholder.container():
        st.markdown("<div style='color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:1.2px; font-weight:700; margin-bottom:10px;'>Match Stats</div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style='display:grid; grid-template-columns: 1fr 1fr; gap:8px;'>
            <div style='background:linear-gradient(135deg, rgba(59,130,246,0.10), rgba(59,130,246,0.03)); border:1px solid rgba(59,130,246,0.2); border-radius:10px; padding:10px 12px;'>
                <div style='color:#93c5fd; font-size:22px; font-weight:800;'>{_kpis['fours']}</div>
                <div style='color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:1px;'>Fours</div>
            </div>
            <div style='background:linear-gradient(135deg, rgba(168,85,247,0.10), rgba(168,85,247,0.03)); border:1px solid rgba(168,85,247,0.2); border-radius:10px; padding:10px 12px;'>
                <div style='color:#c4b5fd; font-size:22px; font-weight:800;'>{_kpis['sixes']}</div>
                <div style='color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:1px;'>Sixes</div>
            </div>
            <div style='background:linear-gradient(135deg, rgba(239,68,68,0.10), rgba(239,68,68,0.03)); border:1px solid rgba(239,68,68,0.2); border-radius:10px; padding:10px 12px;'>
                <div style='color:#fca5a5; font-size:22px; font-weight:800;'>{_kpis['wickets']}</div>
                <div style='color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:1px;'>Wickets</div>
            </div>
            <div style='background:linear-gradient(135deg, rgba(148,163,184,0.10), rgba(148,163,184,0.03)); border:1px solid rgba(148,163,184,0.2); border-radius:10px; padding:10px 12px;'>
                <div style='color:#cbd5e1; font-size:22px; font-weight:800;'>{_kpis['dots']}</div>
                <div style='color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:1px;'>Dots</div>
            </div>
        </div>
        <div style='margin-top:10px; padding:10px 12px; background:linear-gradient(135deg, rgba(19,168,124,0.10), rgba(19,168,124,0.03)); border:1px solid rgba(19,168,124,0.2); border-radius:10px;'>
            <div style='display:flex; justify-content:space-between; align-items:baseline;'>
                <div>
                    <div style='color:#6ee7b7; font-size:22px; font-weight:800;'>{_kpis['runs']}</div>
                    <div style='color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:1px;'>Total Runs</div>
                </div>
                <div style='color:#94a3b8; font-size:12px;'>{_kpis['balls']} balls</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

if show_commentary_panel:
    _hi_moments = _fetch_highlight_moments(match["match_id"], limit=6)
    with commentary_placeholder.container():
        st.markdown("<div style='color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:1.2px; font-weight:700; margin:16px 0 10px 0;'>Key Moments</div>", unsafe_allow_html=True)
        if _hi_moments.empty:
            st.caption("Moments will appear when a boundary or wicket occurs.")
        else:
            for _, r in _hi_moments.iterrows():
                d = r.to_dict()
                over = f"O{int(d['over'])}.{int(d['ball'])}"
                team_code = team_short(d["batting_team"])
                if d["is_wicket"]:
                    icon = "<span style='background:#ef4444;color:#fff;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:800;letter-spacing:0.5px;'>OUT</span>"
                    txt = f"<b>{d.get('player_out') or d['batter']}</b> out"
                elif d["runs_batter"] == 6:
                    icon = "<span style='background:#a855f7;color:#fff;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:800;letter-spacing:0.5px;'>SIX</span>"
                    txt = f"<b>{d['batter']}</b> smashes it"
                else:
                    icon = "<span style='background:#3b82f6;color:#fff;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:800;letter-spacing:0.5px;'>FOUR</span>"
                    txt = f"<b>{d['batter']}</b> nicely placed"
                st.markdown(f"""
                <div style='padding:8px 10px; background:rgba(255,255,255,0.03); border-radius:8px; margin-bottom:5px; font-size:12px; color:#cbd5e1;'>
                    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;'>
                        {icon}
                        <span style='color:#64748b; font-family:monospace; font-size:11px;'>{over} · {team_code}</span>
                    </div>
                    <div>{txt}</div>
                    <div style='color:#64748b; font-size:11px; margin-top:2px;'>Score {int(d['innings_score'])}/{int(d['innings_wickets'])}</div>
                </div>
                """, unsafe_allow_html=True)


# ---------------- Live ticker ---------------- #
tick = _fetch_ticker_events(match["match_id"], n=25)
if not tick.empty:
    snippets = [_ticker_snippet(r.to_dict()) for _, r in tick.iterrows()]
    joiner = "<span class='sep'>|</span>"
    # duplicate content so the scroll animation loops seamlessly
    marquee = joiner.join(snippets + snippets)
    st.markdown(f"""
    <div class='ticker-wrap'>
        <div class='ticker-tag'>LIVE</div>
        <div class='ticker-scroll'>{marquee}</div>
    </div>
    """, unsafe_allow_html=True)


# ---------------- Hero ---------------- #
pill = ("<span class='finished-pill'>FINISHED</span>"
        if match.get("result_text") else "<span class='live-pill'>LIVE</span>")
result_line = match.get("result_text") or (
    f"Toss: {match['toss_winner']} chose to {match['toss_decision']}"
)
st.markdown(f"""
<div class='hero'><div class='hero-inner'>
    <div>
        {pill}
        <span class='hero-title'>{match['team_a']}</span>
        <span class='hero-vs'>vs</span>
        <span class='hero-title'>{match['team_b']}</span>
    </div>
    <div class='hero-sub'>{match['venue']} &nbsp;·&nbsp; {result_line}</div>
</div></div>
""", unsafe_allow_html=True)


# ---------------- Score cards ---------------- #
score_df = _fetch_live_score(match["match_id"])
wp = _fetch_win_prob(match["match_id"])

cols = st.columns(2)
for _, row in score_df.iterrows():
    idx = int(row["innings"]) - 1
    is_current = (idx == int(score_df["innings"].max() - 1)) and not match.get("result_text")
    batting_team = row["batting_team"]
    pal = pal_a if batting_team == match["team_a"] else pal_b
    team_side = "team-a" if batting_team == match["team_a"] else "team-b"
    card_class = f"score-card {team_side}" + (" batting" if is_current else "")

    chase_html = ""
    if row["innings"] == 2 and not pd.isna(row["target"]):
        balls_left = max(0, int(120 - row["overs"] * 6))
        runs_needed = max(0, int(row["target"]) - int(row["score"]))
        rrr = (runs_needed * 6 / balls_left) if balls_left > 0 else 0
        chase_html = (f"<div class='chase-info'>Target {int(row['target'])} · "
                      f"Need <b>{runs_needed}</b> in <b>{balls_left}</b> balls · "
                      f"RRR <b>{rrr:.2f}</b></div>")

    badge_style = f"background:{pal['primary']};color:{pal['text_on']}"
    with cols[idx]:
        st.markdown(f"""
        <div class='{card_class}'>
            <span class='team-badge' style='{badge_style}'>{team_short(batting_team)}</span>
            <div class='team-name'>Innings {int(row['innings'])} · {batting_team}</div>
            <div class='score'>{int(row['score'])}<span class='score-sep'>/</span>{int(row['wickets'])}</div>
            <div class='score-sub'>{row['overs']} overs</div>
            {chase_html}
        </div>
        """, unsafe_allow_html=True)


# ---------------- Current over ---------------- #
over_balls = _fetch_current_over_balls(match["match_id"])
if not over_balls.empty:
    st.markdown("<div class='section-title'>This Over</div>", unsafe_allow_html=True)
    chips = []
    for _, row in over_balls.iterrows():
        cls, label = _chip_class(row.to_dict())
        chips.append(f"<span class='ball-chip {cls}'>{label}</span>")
    st.markdown(f"<div class='ball-row'>{''.join(chips)}</div>", unsafe_allow_html=True)


# ---------------- Momentum + Confidence gauge ---------------- #
st.markdown("<div class='section-title'>Momentum &amp; Confidence</div>", unsafe_allow_html=True)
col_mom, col_gauge = st.columns([3, 2])

with col_mom:
    momentum = _fetch_momentum(match["match_id"], overs_back=3)
    if momentum:
        # find the leader for scaling
        max_runs = max(v["runs"] for v in momentum.values()) or 1
        html_rows = []
        for team_name in [match["team_a"], match["team_b"]]:
            data = momentum.get(team_name)
            if not data:
                continue
            pct = int(100 * data["runs"] / max(max_runs, 15))
            pal = pal_a if team_name == match["team_a"] else pal_b
            wk_html = f"<span class='wk'>-{data['wickets']}W</span>" if data["wickets"] else ""
            html_rows.append(f"""
            <div class='momentum-row'>
                <div class='momentum-label'>{team_short(team_name)}</div>
                <div class='momentum-bar-outer'>
                    <div class='momentum-bar-inner' style='width:{pct}%; background: linear-gradient(90deg, {pal['primary']}, {pal['accent']});'>
                        {data['runs']}
                    </div>
                </div>
                <div class='momentum-value'>{data['runs']} runs{wk_html}</div>
            </div>
            """)
        st.markdown(
            f"<div class='momentum-wrap'>"
            f"<div style='color:#94a3b8; font-size:12px; margin-bottom:12px; text-transform:uppercase; letter-spacing:1px;'>Last 3 overs</div>"
            f"{''.join(html_rows)}"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Momentum will appear after over 1.")

with col_gauge:
    if not wp.empty:
        last = wp.iloc[-1]
        # gauge shows Team A's win probability
        prob_a_pct = float(last["win_prob_team_a"]) * 100
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=prob_a_pct,
            number={"suffix": "%", "font": {"size": 40, "color": "#fff"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#475569", "tickfont": {"color": "#94a3b8"}},
                "bar": {"color": pal_a["primary"], "thickness": 0.3},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 30],  "color": "rgba(239,68,68,0.15)"},
                    {"range": [30, 70], "color": "rgba(251,191,36,0.15)"},
                    {"range": [70, 100],"color": "rgba(16,185,129,0.15)"},
                ],
                "threshold": {"line": {"color": pal_a["accent"], "width": 4},
                              "thickness": 0.8, "value": prob_a_pct},
            },
            title={
                "text": (
                    f"<span style='color:#94a3b8;font-size:12px;letter-spacing:1.5px'>WIN PROBABILITY</span>"
                    f"<br><span style='color:{pal_a['primary']};font-size:14px;font-weight:700'>{team_short(match['team_a'])}</span>"
                ),
                "font": {"size": 12, "color": "#94a3b8"},
            },
        ))
        fig.update_layout(
            height=240,
            margin=dict(l=10, r=10, t=60, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            font={"color": "#e8ecf3"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Predictions loading...")


# ---------------- Win-prob line + Worm chart + Manhattan ---------------- #
st.markdown("<div class='section-title'>Win Probability Trajectory</div>", unsafe_allow_html=True)

if wp.empty:
    st.info("Waiting for first prediction...")
else:
    wp = wp.copy()
    wp["ball_idx"] = range(len(wp))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=wp["ball_idx"], y=wp["win_prob_team_a"] * 100,
        name=match["team_a"], mode="lines",
        line=dict(width=3.5, color=pal_a["primary"], shape="spline"),
        fill="tozeroy",
        fillcolor=pal_a["primary"].replace(")", ",0.10)").replace("#", "rgba(0,0,0,0.10)") if not pal_a["primary"].startswith("#") else f"rgba({int(pal_a['primary'][1:3],16)},{int(pal_a['primary'][3:5],16)},{int(pal_a['primary'][5:7],16)},0.12)",
    ))
    fig.add_trace(go.Scatter(
        x=wp["ball_idx"], y=wp["win_prob_team_b"] * 100,
        name=match["team_b"], mode="lines",
        line=dict(width=3.5, color=pal_b["primary"], shape="spline"),
        fill="tozeroy",
        fillcolor=f"rgba({int(pal_b['primary'][1:3],16)},{int(pal_b['primary'][3:5],16)},{int(pal_b['primary'][5:7],16)},0.10)",
    ))
    fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.15)")
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(title="Win probability (%)", range=[0, 100],
                   gridcolor="rgba(255,255,255,0.05)", color="#94a3b8"),
        xaxis=dict(title="Ball number",
                   gridcolor="rgba(255,255,255,0.05)", color="#94a3b8"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#e8ecf3")),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


st.markdown("<div class='section-title'>Worm Chart &amp; Manhattan</div>", unsafe_allow_html=True)
prog = _fetch_over_progression(match["match_id"])
col_worm, col_man = st.columns(2)

with col_worm:
    st.markdown("<div style='color:#94a3b8; font-size:13px; margin-bottom:8px'>Cumulative runs</div>",
                unsafe_allow_html=True)
    if prog.empty:
        st.info("Waiting for over 1...")
    else:
        fig = go.Figure()
        for inn in sorted(prog["innings"].unique()):
            sub = prog[prog["innings"] == inn]
            with get_conn(read_only=True) as conn:
                team = conn.execute("""
                    SELECT ANY_VALUE(batting_team) FROM bronze.balls_raw
                     WHERE match_id=? AND innings=?
                """, [match["match_id"], int(inn)]).fetchone()[0]
            pal = pal_a if team == match["team_a"] else pal_b
            fig.add_trace(go.Scatter(
                x=sub["over"] + 1, y=sub["cumulative_score"],
                name=f"{team_short(team)} (I{int(inn)})",
                mode="lines+markers",
                line=dict(width=3, color=pal["primary"], shape="spline"),
                marker=dict(size=6, color=pal["primary"]),
            ))
        # target line if innings 2 exists
        with get_conn(read_only=True) as conn:
            target_row = conn.execute("""
                SELECT MAX(target) FROM bronze.balls_raw WHERE match_id=? AND innings=2
            """, [match["match_id"]]).fetchone()
            target = target_row[0] if target_row else None
        if target is not None:
            fig.add_hline(y=int(target), line_dash="dash", line_color="#fbbf24",
                          annotation_text=f"Target {int(target)}",
                          annotation_position="top left",
                          annotation_font_color="#fbbf24")
        fig.update_layout(
            height=310, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Runs", gridcolor="rgba(255,255,255,0.05)", color="#94a3b8"),
            xaxis=dict(title="Over", gridcolor="rgba(255,255,255,0.05)", color="#94a3b8"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#e8ecf3")),
        )
        st.plotly_chart(fig, use_container_width=True)

with col_man:
    st.markdown("<div style='color:#94a3b8; font-size:13px; margin-bottom:8px'>Runs per over (wickets marked red)</div>",
                unsafe_allow_html=True)
    if prog.empty:
        st.info("Waiting...")
    else:
        # focus on the most recent innings for legibility
        latest_inn = int(prog["innings"].max())
        sub = prog[prog["innings"] == latest_inn].copy()
        with get_conn(read_only=True) as conn:
            team = conn.execute("""
                SELECT ANY_VALUE(batting_team) FROM bronze.balls_raw
                 WHERE match_id=? AND innings=?
            """, [match["match_id"], latest_inn]).fetchone()[0]
        pal = pal_a if team == match["team_a"] else pal_b
        colors = ["#ef4444" if w > 0 else pal["primary"] for w in sub["wickets_in_over"]]
        fig = go.Figure(go.Bar(
            x=sub["over"] + 1, y=sub["runs_in_over"],
            marker_color=colors, marker_line_width=0,
            text=[f"{r}{' -'+str(w) if w else ''}" for r, w in zip(sub["runs_in_over"], sub["wickets_in_over"])],
            textposition="outside",
            textfont=dict(color="#e8ecf3", size=11),
        ))
        fig.update_layout(
            height=310, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", color="#94a3b8"),
            xaxis=dict(title=f"Over ({team_short(team)} innings)", gridcolor="rgba(255,255,255,0.05)", color="#94a3b8"),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------- AI highlights + Expert take ---------------- #
st.markdown("<div class='section-title'>AI Analyst</div>", unsafe_allow_html=True)

# Highlights (cached ~2 min so we don't spam Gemini)
@st.cache_data(ttl=120)
def _cached_highlights(match_id: str, result_text: str | None) -> str:
    with get_conn(read_only=True) as conn:
        batters = conn.execute("""
            SELECT batter, runs FROM gold.batter_scorecard
             WHERE match_id=? ORDER BY runs DESC LIMIT 1
        """, [match_id]).fetchone()
        bowlers = conn.execute("""
            SELECT bowler, wickets FROM gold.bowler_scorecard
             WHERE match_id=? ORDER BY wickets DESC, economy ASC LIMIT 1
        """, [match_id]).fetchone()
        innings = conn.execute("""
            SELECT innings, ANY_VALUE(batting_team), MAX(innings_score), MAX(innings_wickets)
              FROM bronze.balls_raw WHERE match_id=? GROUP BY innings ORDER BY innings
        """, [match_id]).fetchall()
    summary = {
        "team_a": match["team_a"], "team_b": match["team_b"],
        "result_text": result_text,
        "top_batter": batters[0] if batters else None,
        "top_batter_runs": batters[1] if batters else 0,
        "top_bowler": bowlers[0] if bowlers else None,
        "top_bowler_wickets": bowlers[1] if bowlers else 0,
    }
    for i, t, s, w in innings:
        summary[f"inn{i}_team"] = t
        summary[f"inn{i}_score"] = int(s)
        summary[f"inn{i}_wickets"] = int(w)
    return generate_highlights(summary)


try:
    highlights = _cached_highlights(match["match_id"], match.get("result_text"))
    st.markdown(f"""
    <div class='highlights-card'>
        <span class='badge'>MATCH HIGHLIGHTS</span>
        {highlights}
    </div>
    """, unsafe_allow_html=True)
except Exception:
    pass

# Expert take
if not score_df.empty:
    latest_inn_row = score_df.iloc[-1]
    latest_wp_batting = None
    if not wp.empty:
        last = wp.iloc[-1]
        latest_wp_batting = float(
            last["win_prob_team_a"] if latest_inn_row["batting_team"] == match["team_a"]
            else last["win_prob_team_b"]
        )
    _target_raw = latest_inn_row["target"]
    _has_target = not pd.isna(_target_raw)
    _target_int = int(_target_raw) if _has_target else None
    state = {
        "innings": int(latest_inn_row["innings"]),
        "batting_team": latest_inn_row["batting_team"],
        "score": int(latest_inn_row["score"]),
        "wickets": int(latest_inn_row["wickets"]),
        "overs_completed": float(latest_inn_row["overs"]),
        "target": _target_int,
        "runs_needed": (_target_int - int(latest_inn_row["score"])) if _has_target else None,
        "required_run_rate": (
            ((_target_int - int(latest_inn_row["score"])) * 6 /
             max(1, int(120 - latest_inn_row["overs"] * 6)))
            if _has_target else None
        ),
    }
    take = explain_match_state(state, latest_wp_batting)
    st.markdown(f"""
    <div class='insight-card'>
        <span class='badge'>EXPERT TAKE</span>
        {take}
    </div>
    """, unsafe_allow_html=True)


# ---------------- Player cards (top 6 batters) ---------------- #
st.markdown("<div class='section-title'>Top Performers</div>", unsafe_allow_html=True)
b = _fetch_batters(match["match_id"])
if not b.empty:
    top_batters = b.sort_values("runs", ascending=False).head(6)
    cards_html = []
    for _, r in top_batters.iterrows():
        team = None
        # look up batting team from bronze
        with get_conn(read_only=True) as conn:
            row = conn.execute("""
                SELECT ANY_VALUE(batting_team) FROM bronze.balls_raw
                 WHERE match_id=? AND innings=? AND batter=?
            """, [match["match_id"], int(r["innings"]), r["batter"]]).fetchone()
            team = row[0] if row else None
        tint = "team-a-tint" if team == match["team_a"] else "team-b-tint"
        role_txt = "OUT" if r["is_out"] else "NOT OUT"
        sr = float(r["strike_rate"])
        sr_pct = min(int(sr / 250 * 100), 100)  # cap the visual bar at SR 250
        cards_html.append(f"""
        <div class='player-card {tint}'>
            <div class='player-name'>{r['batter']}</div>
            <div class='player-role'>{team_short(team) if team else '?'} · {role_txt}</div>
            <div class='player-stats'>
                <div class='stat-block'>
                    <div class='stat-value'>{int(r['runs'])}</div>
                    <div class='stat-label'>Runs</div>
                </div>
                <div class='stat-block'>
                    <div class='stat-value'>{int(r['balls_faced'])}</div>
                    <div class='stat-label'>Balls</div>
                </div>
                <div class='stat-block'>
                    <div class='stat-value'>{int(r['fours'])}·{int(r['sixes'])}</div>
                    <div class='stat-label'>4s · 6s</div>
                </div>
                <div class='stat-block'>
                    <div class='stat-value'>{sr:.0f}</div>
                    <div class='stat-label'>SR</div>
                </div>
            </div>
            <div class='sr-bar'><div class='sr-bar-fill' style='width:{sr_pct}%'></div></div>
        </div>
        """)
    st.markdown(f"<div class='player-grid'>{''.join(cards_html)}</div>", unsafe_allow_html=True)
else:
    st.info("Player stats will appear after over 1 completes.")


# ---------------- Full scorecards (tables) ---------------- #
st.markdown("<div class='section-title'>Full Scorecards</div>", unsafe_allow_html=True)
col_bat, col_bowl = st.columns(2)
with col_bat:
    st.markdown("<div style='color:#94a3b8; font-size:13px; margin-bottom:6px'>Batters</div>", unsafe_allow_html=True)
    if not b.empty:
        show_b = b.rename(columns={
            "innings": "Inn", "batter": "Batter", "runs": "R", "balls_faced": "B",
            "fours": "4s", "sixes": "6s", "strike_rate": "SR",
        })[["Inn", "Batter", "R", "B", "4s", "6s", "SR"]]
        st.dataframe(show_b, use_container_width=True, hide_index=True, height=min(400, 42 * (len(show_b) + 1) + 20))
with col_bowl:
    st.markdown("<div style='color:#94a3b8; font-size:13px; margin-bottom:6px'>Bowlers</div>", unsafe_allow_html=True)
    bw = _fetch_bowlers(match["match_id"])
    if not bw.empty:
        show_bw = bw.rename(columns={
            "innings": "Inn", "bowler": "Bowler", "overs": "O", "runs_conceded": "R",
            "wickets": "W", "economy": "Econ", "dot_balls": "Dots",
        })[["Inn", "Bowler", "O", "R", "W", "Econ", "Dots"]]
        st.dataframe(show_bw, use_container_width=True, hide_index=True, height=min(400, 42 * (len(show_bw) + 1) + 20))


# ---------------- Ball-by-ball feed ---------------- #
st.markdown("<div class='section-title'>Live Ball-by-Ball</div>", unsafe_allow_html=True)
rb = _fetch_recent_balls(match["match_id"], n=15)
if rb.empty:
    st.info("No balls yet.")
else:
    for _, r in rb.iterrows():
        d = r.to_dict()
        cls, label = _chip_class(d)
        over = f"{int(d['over'])}.{int(d['ball'])}"
        css_class = "wicket" if d["is_wicket"] else ("six" if d["runs_batter"] == 6 else ("four" if d["runs_batter"] == 4 else ""))
        if d["is_wicket"]:
            msg = f"<b>{d.get('player_out') or d['batter']}</b> out ({d.get('dismissal_kind') or 'wicket'})"
        elif d["runs_batter"] > 0:
            msg = f"{d['batter']} scored <b>{d['runs_batter']}</b> off {d['bowler']}"
        elif d["runs_extras"] > 0:
            msg = f"<b>{d.get('extras_kind') or 'extras'}</b> conceded by {d['bowler']}"
        else:
            msg = f"Dot ball · {d['batter']} vs {d['bowler']}"
        st.markdown(f"""
        <div class='ball-line {css_class}'>
            <span class='over-tag'>{over}</span>
            <span class='ball-chip {cls}' style='width:32px;height:32px;font-size:13px'>{label}</span>
            <span class='msg'>{msg}</span>
            <span class='final-score'>{int(d['innings_score'])}/{int(d['innings_wickets'])}</span>
        </div>
        """, unsafe_allow_html=True)


# ---------------- AI chat ---------------- #
if not show_talks_panel:
    pass  # user hid this panel from the sidebar
elif not genai_ready():
    st.markdown("<div class='section-title'>Ask the AI Analyst</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='insight-card' style='background: linear-gradient(135deg, rgba(251,191,36,0.10) 0%, rgba(239,68,68,0.08) 100%); border-color: rgba(251,191,36,0.3)'>
        <span class='badge' style='background:linear-gradient(135deg,#fbbf24,#f59e0b); color:#1a1a1a'>SETUP</span>
        Add your free <b>Google Gemini API key</b> to unlock natural-language questions.
        <br><br>
        <span style='color:#94a3b8'>Get a free key at</span> <a href='https://aistudio.google.com/apikey' target='_blank' style='color:#93c5fd'>aistudio.google.com/apikey</a>
        <span style='color:#94a3b8'>and paste it into the Streamlit Cloud secrets settings.</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("<div class='section-title'>Ask the AI Analyst</div>", unsafe_allow_html=True)
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.markdown("<div style='color:#94a3b8; font-size:13px; margin-bottom:10px'>Try one of these:</div>", unsafe_allow_html=True)
    sample_prompts = [
        "Who has the highest strike rate?",
        "Most economical bowler?",
        "Biggest over of the match?",
        "Predict the final score",
        "Why is the trailing team losing?",
    ]
    cols = st.columns(len(sample_prompts))
    for i, p in enumerate(sample_prompts):
        if cols[i].button(p, key=f"sp_{i}", use_container_width=True):
            st.session_state.pending_prompt = p

    prompt = st.chat_input("Ask anything about this match...")
    if "pending_prompt" in st.session_state and st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    for entry in st.session_state.chat_history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if entry.get("sql"):
                with st.expander("View SQL & data"):
                    st.code(entry["sql"], language="sql")
                    if entry.get("results") is not None and not entry["results"].empty:
                        st.dataframe(entry["results"], use_container_width=True, hide_index=True)

    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing the data..."):
                try:
                    answer = ask(prompt)
                    st.markdown(answer.natural_answer)
                    with st.expander("View SQL & data"):
                        st.code(answer.sql, language="sql")
                        if not answer.results.empty:
                            st.dataframe(answer.results, use_container_width=True, hide_index=True)
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": answer.natural_answer,
                        "sql": answer.sql,
                        "results": answer.results,
                    })
                except Exception as e:
                    st.error(f"Something went wrong: {e}")


# ---------------- Footer ---------------- #
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align:center; color:#475569; font-size:12px; padding-bottom:24px'>"
    "CricketPulse · Kafka + Airflow + DuckDB + scikit-learn + LangChain + Gemini · Built for placements"
    "</div>",
    unsafe_allow_html=True,
)
