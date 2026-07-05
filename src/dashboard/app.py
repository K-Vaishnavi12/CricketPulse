"""CricketPulse Streamlit dashboard.

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
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.dashboard.live_sim import (
    is_live_active, live_status, start_new_match, step_live_match, stop_live_match,
)
from src.genai.commentator import explain_match_state
from src.genai.llm import is_configured as genai_ready
from src.genai.sql_agent import ask
from src.warehouse.db import get_conn


# ============================================================================ #
# Page config + global styles
# ============================================================================ #

st.set_page_config(
    page_title="CricketPulse | Live Match Intelligence",
    page_icon="[C]",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
/* Hide the default Streamlit chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Nice fonts */
html, body, [class*="css"]  {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* Background gradient */
[data-testid="stAppViewContainer"] {
    background: radial-gradient(1200px 600px at 10% 0%, #12233a 0%, #0a1424 40%, #060b16 100%);
    color: #e8ecf3;
}
[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: #0a1424; }

/* Hero banner */
.hero {
    padding: 22px 28px;
    border-radius: 20px;
    background: linear-gradient(135deg, rgba(19,168,124,0.15) 0%, rgba(59,130,246,0.15) 100%);
    border: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 22px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.35);
}
.hero-title { font-size: 30px; font-weight: 700; color: #fff; letter-spacing: -0.5px; margin: 0; }
.hero-sub { color: #93a2b8; font-size: 14px; margin-top: 4px; }
.live-pill {
    display: inline-block;
    padding: 4px 12px;
    background: #ef4444;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 999px;
    margin-right: 10px;
    letter-spacing: 0.8px;
    animation: pulse 1.6s ease-in-out infinite;
    vertical-align: middle;
}
.finished-pill {
    display: inline-block;
    padding: 4px 12px;
    background: #10b981;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 999px;
    margin-right: 10px;
    letter-spacing: 0.8px;
    vertical-align: middle;
}
@keyframes pulse {
    0%   { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
    70%  { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
    100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}

/* Score cards */
.score-card {
    border-radius: 18px;
    padding: 20px 24px;
    background: linear-gradient(160deg, #101c2e 0%, #0b1524 100%);
    border: 1px solid rgba(255,255,255,0.06);
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    min-height: 150px;
}
.score-card.batting {
    border-left: 4px solid #13a87c;
    box-shadow: 0 4px 24px rgba(19,168,124,0.2);
}
.score-card .team-name { color: #93a2b8; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; }
.score-card .score { color: #fff; font-size: 44px; font-weight: 800; margin: 6px 0; letter-spacing: -1px; }
.score-card .score-sub { color: #93a2b8; font-size: 14px; }
.score-card .chase-info { color: #fbbf24; font-size: 13px; margin-top: 8px; font-weight: 600; }

/* Section header */
.section-title { color: #fff; font-size: 18px; font-weight: 700; margin: 22px 0 12px 0; }
.section-title .accent { color: #13a87c; }

/* Insight card (AI take) */
.insight-card {
    padding: 18px 22px;
    border-radius: 16px;
    background: linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(139,92,246,0.12) 100%);
    border: 1px solid rgba(139,92,246,0.25);
    color: #e8ecf3;
    font-size: 15px;
    line-height: 1.55;
}
.insight-card .badge {
    display: inline-block;
    background: #8b5cf6;
    color: #fff;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    margin-right: 10px;
    vertical-align: middle;
}

/* Ball chips */
.ball-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px 0; }
.ball-chip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px; height: 36px;
    border-radius: 50%;
    font-weight: 700;
    font-size: 14px;
    color: #fff;
    box-shadow: 0 2px 6px rgba(0,0,0,0.35);
}
.chip-dot { background: #334155; }
.chip-1, .chip-2, .chip-3 { background: #475569; }
.chip-4 { background: #3b82f6; }
.chip-6 { background: #a855f7; }
.chip-w { background: #ef4444; }
.chip-x { background: #f59e0b; color: #1a1a1a; font-size: 11px; }

/* Ball feed line */
.ball-line {
    padding: 10px 14px;
    background: rgba(255,255,255,0.03);
    border-radius: 10px;
    margin-bottom: 6px;
    border-left: 3px solid #334155;
    font-size: 14px;
    color: #e8ecf3;
}
.ball-line.wicket { border-left-color: #ef4444; background: rgba(239,68,68,0.06); }
.ball-line.six    { border-left-color: #a855f7; background: rgba(168,85,247,0.06); }
.ball-line.four   { border-left-color: #3b82f6; background: rgba(59,130,246,0.06); }
.ball-line .over-tag { color: #64748b; font-family: monospace; margin-right: 8px; }

/* Chat */
[data-testid="stChatInput"] {
    background: rgba(255,255,255,0.04);
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.08);
}

/* Suggestion chips */
.stButton>button {
    background: rgba(59,130,246,0.12);
    color: #93c5fd;
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 999px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.15s;
}
.stButton>button:hover {
    background: rgba(59,130,246,0.25);
    border-color: rgba(59,130,246,0.6);
    color: #fff;
}

/* Dataframes */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.06);
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================================ #
# Data access helpers
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
             GROUP BY innings
             ORDER BY innings
        """, [match_id]).df()


@st.cache_data(ttl=3)
def _fetch_win_prob(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, over, ball,
                   win_prob_team_a, win_prob_team_b,
                   predicted_final_score, event_ts
              FROM bronze.predictions_raw
             WHERE match_id = ?
             ORDER BY event_ts
        """, [match_id]).df()


@st.cache_data(ttl=3)
def _fetch_batters(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings AS Inn, batter AS Batter,
                   runs AS R, balls_faced AS B,
                   fours AS "4s", sixes AS "6s",
                   strike_rate AS SR,
                   CASE WHEN is_out THEN 'out ('||COALESCE(dismissal,'?')||')' ELSE 'not out' END AS Status
              FROM gold.batter_scorecard
             WHERE match_id = ?
             ORDER BY innings, runs DESC
        """, [match_id]).df()


@st.cache_data(ttl=3)
def _fetch_bowlers(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings AS Inn, bowler AS Bowler,
                   overs AS O, runs_conceded AS R,
                   wickets AS W, economy AS Econ,
                   dot_balls AS Dots
              FROM gold.bowler_scorecard
             WHERE match_id = ?
             ORDER BY innings, wickets DESC, economy ASC
        """, [match_id]).df()


@st.cache_data(ttl=3)
def _fetch_over_progression(match_id: str) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return conn.execute("""
            SELECT innings, over, runs_in_over, wickets_in_over,
                   cumulative_score, phase
              FROM gold.over_progression
             WHERE match_id = ?
             ORDER BY innings, over
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
             ORDER BY event_ts DESC
             LIMIT ?
        """, [match_id, n]).df()


@st.cache_data(ttl=3)
def _fetch_current_over_balls(match_id: str) -> pd.DataFrame:
    """Get all balls from the most recent over for the visual over-chip strip."""
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
             WHERE match_id=? AND innings=? AND over=?
             ORDER BY ball
        """, [match_id, latest[0], latest[1]]).df()


# ============================================================================ #
# UI helpers
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


def _render_ball_chips(balls_df: pd.DataFrame) -> str:
    if balls_df.empty:
        return "<div class='ball-row'><span style='color:#64748b'>No balls this over yet.</span></div>"
    chips = []
    for _, row in balls_df.iterrows():
        cls, label = _chip_class(row.to_dict())
        chips.append(f"<span class='ball-chip {cls}'>{label}</span>")
    return f"<div class='ball-row'>{''.join(chips)}</div>"


def _render_ball_line(row: dict) -> str:
    cls, label = _chip_class(row)
    tag_html = f"<span class='ball-chip {cls}' style='width:30px;height:30px;font-size:12px'>{label}</span>"
    over = f"{int(row['over'])}.{int(row['ball'])}"
    css_class = "wicket" if row["is_wicket"] else ("six" if row["runs_batter"] == 6 else ("four" if row["runs_batter"] == 4 else ""))
    if row["is_wicket"]:
        text = f"<b>{row.get('player_out') or row['batter']}</b> out ({row.get('dismissal_kind') or 'wicket'})"
    elif row["runs_batter"] > 0:
        text = f"{row['batter']} scores <b>{row['runs_batter']}</b> off {row['bowler']}"
    elif row["runs_extras"] > 0:
        text = f"<b>{row.get('extras_kind') or 'extras'}</b> conceded by {row['bowler']}"
    else:
        text = f"Dot ball. {row['batter']} vs {row['bowler']}"
    return f"""
    <div class='ball-line {css_class}'>
        <span class='over-tag'>{over}</span>
        {tag_html}
        <span style='margin-left:10px'>{text}</span>
        <span style='float:right; color:#93a2b8'>{int(row['innings_score'])}/{int(row['innings_wickets'])}</span>
    </div>
    """


# ============================================================================ #
# Sidebar (minimal, hidden by default)
# ============================================================================ #

with st.sidebar:
    st.markdown("### CricketPulse")
    st.caption("Real-time cricket intelligence")
    st.divider()

    st.markdown("**Live Match Controls**")
    if is_live_active():
        stat = live_status()
        st.success(f"Streaming: {stat['balls_delivered']} balls delivered")
        if st.button("Stop match", use_container_width=True):
            stop_live_match()
            st.rerun()
    else:
        team_a_in = st.text_input("Team A", value="Mumbai Mavericks")
        team_b_in = st.text_input("Team B", value="Chennai Chargers")
        venue_in  = st.text_input("Venue",  value="Wankhede Stadium")
        if st.button("Start live match", type="primary", use_container_width=True):
            start_new_match(team_a_in, team_b_in, venue_in)
            st.rerun()

    st.divider()
    auto_refresh = st.toggle("Live auto-refresh (2s)", value=True)
    if auto_refresh:
        st_autorefresh(interval=2000, key="live_refresh")
    st.divider()
    st.caption(
        "Streaming + ML + GenAI pipeline. "
        "Powered by Kafka, Airflow, DuckDB, scikit-learn, LangChain and Gemini."
    )


# Progress a live match forward every render if one is active
if is_live_active():
    step_live_match(balls_per_tick=3)


# ============================================================================ #
# Main
# ============================================================================ #

match = _fetch_current_match()

if match is None:
    st.markdown("""
    <div class='hero'>
        <div class='hero-title'>CricketPulse</div>
        <div class='hero-sub'>Waiting for the first ball to be bowled...</div>
    </div>
    """, unsafe_allow_html=True)
    st.info("No match data yet. Start streaming a match to see the dashboard come alive.")
    st.stop()


# ---------------- Hero banner ---------------- #
pill = ("<span class='finished-pill'>FINISHED</span>"
        if match.get("result_text") else "<span class='live-pill'>LIVE</span>")
result_line = match.get("result_text") or (
    f"Toss: {match['toss_winner']} chose to {match['toss_decision']}"
)
st.markdown(f"""
<div class='hero'>
    <div>{pill}<span class='hero-title'>{match['team_a']} vs {match['team_b']}</span></div>
    <div class='hero-sub'>{match['venue']} &nbsp;|&nbsp; {result_line}</div>
</div>
""", unsafe_allow_html=True)


# ---------------- Score cards ---------------- #
score_df = _fetch_live_score(match["match_id"])
wp = _fetch_win_prob(match["match_id"])

cols = st.columns(2)
for _, row in score_df.iterrows():
    idx = int(row["innings"]) - 1
    is_current = idx == int(score_df["innings"].max() - 1) and not match.get("result_text")
    chase_html = ""
    if row["innings"] == 2 and row["target"] is not None:
        balls_left = max(0, int(120 - row["overs"] * 6))
        runs_needed = max(0, int(row["target"]) - int(row["score"]))
        rrr = (runs_needed * 6 / balls_left) if balls_left > 0 else 0
        chase_html = f"<div class='chase-info'>Need {runs_needed} in {balls_left} balls  |  RRR {rrr:.2f}</div>"
    card_class = "score-card batting" if is_current else "score-card"
    with cols[idx]:
        st.markdown(f"""
        <div class='{card_class}'>
            <div class='team-name'>Innings {int(row['innings'])} - {row['batting_team']}</div>
            <div class='score'>{int(row['score'])}<span style='color:#64748b'>/</span>{int(row['wickets'])}</div>
            <div class='score-sub'>{row['overs']} overs</div>
            {chase_html}
        </div>
        """, unsafe_allow_html=True)


# ---------------- Current over strip ---------------- #
over_balls = _fetch_current_over_balls(match["match_id"])
if not over_balls.empty:
    st.markdown("<div class='section-title'>This Over</div>", unsafe_allow_html=True)
    st.markdown(_render_ball_chips(over_balls), unsafe_allow_html=True)


# ---------------- Win probability + over-runs ---------------- #
st.markdown("<div class='section-title'>Win Probability <span class='accent'>(ML)</span></div>", unsafe_allow_html=True)

col_wp, col_score = st.columns([3, 2])

with col_wp:
    if wp.empty:
        st.info("Waiting for first prediction...")
    else:
        wp = wp.copy()
        wp["ball_idx"] = range(len(wp))
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=wp["ball_idx"], y=wp["win_prob_team_a"] * 100,
            name=match["team_a"], mode="lines",
            line=dict(width=3, color="#13a87c", shape="spline"),
            fill="tozeroy", fillcolor="rgba(19,168,124,0.12)",
        ))
        fig.add_trace(go.Scatter(
            x=wp["ball_idx"], y=wp["win_prob_team_b"] * 100,
            name=match["team_b"], mode="lines",
            line=dict(width=3, color="#3b82f6", shape="spline"),
            fill="tozeroy", fillcolor="rgba(59,130,246,0.10)",
        ))
        fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.15)")
        fig.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(title="Win probability (%)", range=[0, 100],
                       gridcolor="rgba(255,255,255,0.05)", color="#93a2b8"),
            xaxis=dict(title="Ball number",
                       gridcolor="rgba(255,255,255,0.05)", color="#93a2b8"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#e8ecf3")),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

with col_score:
    prog = _fetch_over_progression(match["match_id"])
    st.markdown("<div style='color:#93a2b8; font-size:14px; margin-bottom:8px'>Runs per over</div>",
                unsafe_allow_html=True)
    if prog.empty:
        st.info("Waiting for over 1 to complete...")
    else:
        color_map = {1: "#13a87c", 2: "#3b82f6"}
        prog = prog.copy()
        prog["Innings"] = prog["innings"].map(lambda i: f"Innings {i}")
        fig = px.bar(
            prog, x="over", y="runs_in_over",
            color="Innings", barmode="group",
            color_discrete_map={"Innings 1": "#13a87c", "Innings 2": "#3b82f6"},
            hover_data={"wickets_in_over": True, "cumulative_score": True, "phase": True},
        )
        fig.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="", gridcolor="rgba(255,255,255,0.05)", color="#93a2b8"),
            xaxis=dict(title="Over", gridcolor="rgba(255,255,255,0.05)", color="#93a2b8"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#e8ecf3")),
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------- AI Expert Take ---------------- #
if not score_df.empty:
    latest_inn_row = score_df.iloc[-1]
    latest_wp_batting = None
    if not wp.empty:
        last = wp.iloc[-1]
        latest_wp_batting = float(
            last["win_prob_team_a"] if latest_inn_row["batting_team"] == match["team_a"]
            else last["win_prob_team_b"]
        )
    state = {
        "innings": int(latest_inn_row["innings"]),
        "batting_team": latest_inn_row["batting_team"],
        "score": int(latest_inn_row["score"]),
        "wickets": int(latest_inn_row["wickets"]),
        "overs_completed": float(latest_inn_row["overs"]),
        "target": int(latest_inn_row["target"]) if latest_inn_row["target"] is not None else None,
        "runs_needed": (int(latest_inn_row["target"]) - int(latest_inn_row["score"]))
                       if latest_inn_row["target"] is not None else None,
        "required_run_rate": (
            ((int(latest_inn_row["target"]) - int(latest_inn_row["score"])) * 6 /
             max(1, int(120 - latest_inn_row["overs"] * 6)))
            if latest_inn_row["target"] is not None else None
        ),
    }
    take = explain_match_state(state, latest_wp_batting)
    st.markdown(f"""
    <div class='insight-card' style='margin-top:18px'>
        <span class='badge'>AI EXPERT TAKE</span>
        {take}
    </div>
    """, unsafe_allow_html=True)


# ---------------- Scorecards ---------------- #
st.markdown("<div class='section-title'>Scorecards</div>", unsafe_allow_html=True)
col_bat, col_bowl = st.columns(2)
with col_bat:
    st.markdown("<div style='color:#93a2b8; font-size:14px; margin-bottom:6px'>Batters</div>",
                unsafe_allow_html=True)
    b = _fetch_batters(match["match_id"])
    if not b.empty:
        st.dataframe(b, use_container_width=True, hide_index=True, height=min(420, 42 * (len(b) + 1) + 20))
    else:
        st.info("Building batter stats...")

with col_bowl:
    st.markdown("<div style='color:#93a2b8; font-size:14px; margin-bottom:6px'>Bowlers</div>",
                unsafe_allow_html=True)
    bw = _fetch_bowlers(match["match_id"])
    if not bw.empty:
        st.dataframe(bw, use_container_width=True, hide_index=True, height=min(420, 42 * (len(bw) + 1) + 20))
    else:
        st.info("Building bowler stats...")


# ---------------- Live commentary feed ---------------- #
st.markdown("<div class='section-title'>Live Commentary</div>", unsafe_allow_html=True)
rb = _fetch_recent_balls(match["match_id"], n=12)
if rb.empty:
    st.info("No balls yet.")
else:
    for _, r in rb.iterrows():
        st.markdown(_render_ball_line(r.to_dict()), unsafe_allow_html=True)


# ---------------- AI Analyst chat ---------------- #
st.markdown("<div class='section-title'>Ask the AI Analyst</div>", unsafe_allow_html=True)

if not genai_ready():
    st.markdown("""
    <div class='insight-card' style='background: linear-gradient(135deg, rgba(251,191,36,0.10) 0%, rgba(239,68,68,0.08) 100%); border-color: rgba(251,191,36,0.3)'>
        <span class='badge' style='background:#fbbf24; color:#1a1a1a'>SETUP</span>
        Add your free <b>Google Gemini API key</b> to enable natural-language questions.
        <br><br>
        <span style='color:#93a2b8'>1. Get a free key at</span> <a href='https://aistudio.google.com/apikey' target='_blank' style='color:#93c5fd'>aistudio.google.com/apikey</a><br>
        <span style='color:#93a2b8'>2. Paste it in the</span> <code>.env</code> <span style='color:#93a2b8'>file next to</span> <code>GEMINI_API_KEY</code>
    </div>
    """, unsafe_allow_html=True)
else:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.markdown("<div style='color:#93a2b8; font-size:13px; margin-bottom:10px'>Try one of these:</div>",
                unsafe_allow_html=True)
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
    "<div style='text-align:center; color:#475569; font-size:12px; padding-bottom:20px'>"
    "CricketPulse - Real-time streaming pipeline + ML + GenAI"
    "</div>",
    unsafe_allow_html=True,
)
