"""Pydantic schemas for the event stream."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


DismissalKind = Literal[
    "bowled",
    "caught",
    "lbw",
    "run out",
    "stumped",
    "caught and bowled",
    "hit wicket",
]


class BallEvent(BaseModel):
    """A single delivery in a T20 match."""

    match_id: str
    innings: int = Field(ge=1, le=2)
    over: int = Field(ge=0, le=25)
    ball: int = Field(ge=1, le=20)  # allow re-bowls after wide/no-ball
    batting_team: str
    bowling_team: str
    batter: str
    non_striker: str
    bowler: str
    runs_batter: int = Field(ge=0)
    runs_extras: int = Field(ge=0)
    extras_kind: Optional[Literal["wide", "no ball", "bye", "leg bye", "penalty"]] = None
    is_wicket: bool = False
    dismissal_kind: Optional[DismissalKind] = None
    player_out: Optional[str] = None
    # snapshot AFTER this ball
    innings_score: int = Field(ge=0)
    innings_wickets: int = Field(ge=0, le=10)
    innings_overs_completed: float = Field(ge=0.0, le=25.0)
    target: Optional[int] = None  # only present in innings 2
    event_ts: datetime

    @property
    def runs_total(self) -> int:
        return self.runs_batter + self.runs_extras


class MatchMeta(BaseModel):
    match_id: str
    team_a: str
    team_b: str
    venue: str
    toss_winner: str
    toss_decision: Literal["bat", "field"]
    start_ts: datetime


class Prediction(BaseModel):
    match_id: str
    innings: int
    over: int
    ball: int
    win_prob_team_a: float = Field(ge=0.0, le=1.0)
    win_prob_team_b: float = Field(ge=0.0, le=1.0)
    predicted_final_score: Optional[int] = None
    event_ts: datetime
