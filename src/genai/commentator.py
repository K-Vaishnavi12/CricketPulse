"""AI cricket commentator - turns numbers into engaging commentary lines.

Two modes:
    1. `describe_ball(ball, prediction)` -> one-line commentary of what just happened
    2. `explain_match_state(state)` -> a 3-sentence "expert take" on the current match
"""
from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.common.logging import get_logger
from src.genai.llm import get_llm, is_configured

log = get_logger("genai.commentator")


BALL_SYSTEM = """
You are Ravi Aroundtable, a witty, warm, and slightly dramatic Indian cricket commentator.
Given the JSON of a single ball, respond with ONE short commentary line (max 25 words).
- React to boundaries, wickets, dot balls, extras with different energy.
- Occasionally reference the match situation (target chase, big over, milestone).
- Do NOT list numbers back mechanically. Sound human.
- Never use markdown, quotes, or line breaks.
""".strip()


STATE_SYSTEM = """
You are an experienced T20 analyst on air. Given the current match state and the
latest ML win-probability, write a 2-3 sentence "expert take" that:
    - names the phase of the match (powerplay/middle/death)
    - highlights the momentum shift or key threat
    - gives a crisp tactical suggestion for the trailing team
Keep it to 60 words max. No markdown.
""".strip()


def describe_ball(ball: dict, prediction: Optional[dict] = None) -> str:
    """Commentate on one ball. Falls back to a rule-based line if LLM not configured."""
    if not is_configured():
        return _fallback_ball_line(ball)

    llm = get_llm(temperature=0.7)
    context = {
        "over": f"{ball['over']}.{ball['ball']}",
        "innings": ball["innings"],
        "batter": ball["batter"],
        "bowler": ball["bowler"],
        "runs_batter": ball["runs_batter"],
        "runs_extras": ball["runs_extras"],
        "extras_kind": ball.get("extras_kind"),
        "is_wicket": ball["is_wicket"],
        "dismissal_kind": ball.get("dismissal_kind"),
        "score": f"{ball['innings_score']}/{ball['innings_wickets']}",
        "batting_team": ball["batting_team"],
        "target": ball.get("target"),
        "win_prob_batting": (
            prediction.get("win_prob_team_a")
            if prediction and ball["batting_team"] == prediction.get("team_a_name")
            else (prediction.get("win_prob_team_b") if prediction else None)
        ),
    }
    try:
        reply = llm.invoke([
            SystemMessage(content=BALL_SYSTEM),
            HumanMessage(content=str(context)),
        ]).content
        return reply.strip().replace("\n", " ")
    except Exception as e:
        log.warning(f"Commentator LLM failed: {e}")
        return _fallback_ball_line(ball)


def explain_match_state(state: dict, win_prob_batting: Optional[float] = None) -> str:
    """One-paragraph 'expert take'."""
    if not is_configured():
        return _fallback_state_line(state, win_prob_batting)

    llm = get_llm(temperature=0.5)
    payload = {
        **state,
        "win_prob_batting_team": win_prob_batting,
    }
    try:
        reply = llm.invoke([
            SystemMessage(content=STATE_SYSTEM),
            HumanMessage(content=str(payload)),
        ]).content
        return reply.strip()
    except Exception as e:
        log.warning(f"State-explanation LLM failed: {e}")
        return _fallback_state_line(state, win_prob_batting)


# --------------------------------------------------------------------------- #
# Fallbacks (no API key configured or LLM errored)
# --------------------------------------------------------------------------- #

def _fallback_ball_line(ball: dict) -> str:
    if ball.get("is_wicket"):
        return f"OUT! {ball.get('player_out') or ball['batter']} departs. {ball['batting_team']} {ball['innings_score']}/{ball['innings_wickets']}."
    if ball["runs_batter"] == 6:
        return f"SIX! {ball['batter']} smashes it out of the ground. {ball['batting_team']} now {ball['innings_score']}/{ball['innings_wickets']}."
    if ball["runs_batter"] == 4:
        return f"FOUR! Cracking shot by {ball['batter']}. {ball['innings_score']}/{ball['innings_wickets']}."
    if ball["runs_extras"] > 0:
        return f"Extras: {ball.get('extras_kind') or 'extras'} - {ball['runs_extras']} run(s). Score {ball['innings_score']}/{ball['innings_wickets']}."
    if ball["runs_batter"] == 0:
        return f"Dot ball. Bowler {ball['bowler']} keeps it tight. {ball['innings_score']}/{ball['innings_wickets']}."
    return f"{ball['runs_batter']} run{'s' if ball['runs_batter']>1 else ''} taken. {ball['innings_score']}/{ball['innings_wickets']}."


def _fallback_state_line(state: dict, wp: Optional[float]) -> str:
    innings = state.get("innings", 1)
    overs = state.get("overs_completed", 0)
    score = state.get("score", 0)
    wkts = state.get("wickets", 0)
    if innings == 2 and state.get("target"):
        rrr = state.get("required_run_rate") or 0
        return (
            f"{state.get('batting_team', 'Batting side')} need {state.get('runs_needed', 0)} "
            f"in {int(120 - overs*6)} balls at {rrr:.1f} RPO. They are {score}/{wkts} with "
            f"{10 - wkts} wickets in hand. Win probability sits at {(wp or 0)*100:.0f}%."
        )
    return (
        f"{state.get('batting_team', 'Batting side')} are {score}/{wkts} after {overs} overs. "
        f"Batting side win probability {(wp or 0)*100:.0f}%. Building phase, look for a big finish."
    )
