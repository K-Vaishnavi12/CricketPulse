"""In-memory tracker of every live match so we can build inference features fast."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MatchTracker:
    match_id: str
    team_a: str
    team_b: str
    # innings 1
    inn1_batting_team: Optional[str] = None
    inn1_final_score: Optional[int] = None
    inn1_final_wickets: Optional[int] = None
    inn1_final_overs: Optional[float] = None
    # innings 2 live
    inn2_batting_team: Optional[str] = None
    inn2_score: int = 0
    inn2_wickets: int = 0
    inn2_overs_completed: float = 0.0
    target: Optional[int] = None
    # innings 1 live
    inn1_score: int = 0
    inn1_wickets: int = 0
    inn1_overs_completed: float = 0.0

    current_innings: int = 1


class LiveMatchState:
    """Tracks every open match. Not persistent; rebuilt from bronze on restart."""

    def __init__(self):
        self.matches: Dict[str, MatchTracker] = {}

    def register_match(self, match_id: str, team_a: str, team_b: str) -> None:
        self.matches[match_id] = MatchTracker(match_id=match_id, team_a=team_a, team_b=team_b)

    def _ensure(self, match_id: str) -> MatchTracker:
        if match_id not in self.matches:
            # unknown match (consumer joined mid-stream) - seed a stub
            self.matches[match_id] = MatchTracker(match_id=match_id, team_a="?", team_b="?")
        return self.matches[match_id]

    def update_from_ball(self, ball: dict) -> None:
        m = self._ensure(ball["match_id"])
        innings = ball["innings"]
        m.current_innings = innings
        if innings == 1:
            if m.inn1_batting_team is None:
                m.inn1_batting_team = ball["batting_team"]
            m.inn1_score = ball["innings_score"]
            m.inn1_wickets = ball["innings_wickets"]
            m.inn1_overs_completed = ball["innings_overs_completed"]
        else:  # innings 2
            if m.inn2_batting_team is None:
                m.inn2_batting_team = ball["batting_team"]
                # freeze innings 1 finals when innings 2 starts
                m.inn1_final_score = m.inn1_score
                m.inn1_final_wickets = m.inn1_wickets
                m.inn1_final_overs = m.inn1_overs_completed
            m.inn2_score = ball["innings_score"]
            m.inn2_wickets = ball["innings_wickets"]
            m.inn2_overs_completed = ball["innings_overs_completed"]
            m.target = ball.get("target")

    def feature_vector(self, match_id: str) -> Optional[dict]:
        """Build the feature dict the ML model expects."""
        m = self.matches.get(match_id)
        if m is None:
            return None

        if m.current_innings == 1:
            balls_bowled = int(round(m.inn1_overs_completed * 6))
            balls_remaining = max(0, 120 - balls_bowled)
            wickets_left = 10 - m.inn1_wickets
            current_rr = (m.inn1_score / m.inn1_overs_completed) if m.inn1_overs_completed > 0 else 0.0
            return {
                "innings": 1,
                "batting_team": m.inn1_batting_team or m.team_a,
                "bowling_team": m.team_b if m.inn1_batting_team == m.team_a else m.team_a,
                "score": m.inn1_score,
                "wickets": m.inn1_wickets,
                "overs_completed": m.inn1_overs_completed,
                "balls_remaining": balls_remaining,
                "wickets_left": wickets_left,
                "current_run_rate": current_rr,
                "target": None,
                "required_run_rate": None,
                "runs_needed": None,
                "team_a": m.team_a,
                "team_b": m.team_b,
            }
        else:
            balls_bowled = int(round(m.inn2_overs_completed * 6))
            balls_remaining = max(0, 120 - balls_bowled)
            wickets_left = 10 - m.inn2_wickets
            current_rr = (m.inn2_score / m.inn2_overs_completed) if m.inn2_overs_completed > 0 else 0.0
            runs_needed = (m.target or 0) - m.inn2_score
            required_rr = (runs_needed * 6.0 / balls_remaining) if balls_remaining > 0 else 99.0
            return {
                "innings": 2,
                "batting_team": m.inn2_batting_team or m.team_b,
                "bowling_team": m.team_a if m.inn2_batting_team == m.team_b else m.team_b,
                "score": m.inn2_score,
                "wickets": m.inn2_wickets,
                "overs_completed": m.inn2_overs_completed,
                "balls_remaining": balls_remaining,
                "wickets_left": wickets_left,
                "current_run_rate": current_rr,
                "target": m.target,
                "required_run_rate": required_rr,
                "runs_needed": runs_needed,
                "team_a": m.team_a,
                "team_b": m.team_b,
            }
