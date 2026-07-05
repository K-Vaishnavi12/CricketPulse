"""AI-powered match highlights: one-paragraph broadcast-style recap."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.genai.llm import call_with_fallback, get_llm, is_configured


SYSTEM = """
You are the opening-line writer for a cricket highlights show. Given a match
summary, write ONE punchy 2-3 sentence broadcast recap. Include the winner,
key player performance, and the moment the match tilted. Style: warm, expert,
never robotic. Never use markdown or bullet points. Max 60 words.
""".strip()


def generate_highlights(summary: dict) -> str:
    """summary keys: team_a, team_b, winner, inn1_team, inn1_score, inn1_wickets,
    inn2_team, inn2_score, inn2_wickets, top_batter, top_batter_runs,
    top_bowler, top_bowler_wickets, result_text."""
    fallback = _fallback(summary)
    if not is_configured():
        return fallback

    def _call() -> str:
        llm = get_llm(temperature=0.55)
        reply = llm.invoke([
            SystemMessage(content=SYSTEM),
            HumanMessage(content=str(summary)),
        ]).content
        return reply.strip().replace("\n", " ")

    return call_with_fallback(_call, fallback=fallback)


def _fallback(s: dict) -> str:
    result = s.get("result_text") or "Match in progress"
    top_bat = s.get("top_batter") or "Nobody"
    top_bat_r = s.get("top_batter_runs") or 0
    top_bowl = s.get("top_bowler") or "Nobody"
    top_bowl_w = s.get("top_bowler_wickets") or 0
    return (
        f"{result}. {top_bat} led the batting with {top_bat_r} runs, "
        f"while {top_bowl} took {top_bowl_w} wicket(s) to swing the momentum."
    )
