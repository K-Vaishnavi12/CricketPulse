"""Feature engineering for the win-probability model.

We build one row per ball, then the ML label is:
    * innings 1 : did the batting team WIN the match? (0/1)
    * innings 2 : did the batting team CHASE successfully? (0/1)

Features are numerical only (no team identity leaks) so the model generalizes
to any team names, real or synthetic.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd


FEATURE_COLUMNS: List[str] = [
    "innings",
    "score",
    "wickets",
    "overs_completed",
    "balls_remaining",
    "wickets_left",
    "current_run_rate",
    "target_or_zero",           # 0 in innings 1
    "runs_needed_or_zero",      # 0 in innings 1
    "required_run_rate_or_zero",# 0 in innings 1
    "run_rate_diff",            # current - required (innings 2)
    "phase_powerplay",
    "phase_middle",
    "phase_death",
]


def _phase_flags(over: int) -> Dict[str, int]:
    return {
        "phase_powerplay": int(over < 6),
        "phase_middle":    int(6 <= over < 15),
        "phase_death":     int(over >= 15),
    }


def build_features_row(state: dict) -> Dict[str, float]:
    """Turn a `LiveMatchState.feature_vector` dict into the model's feature row."""
    innings = state["innings"]
    over = int(state["overs_completed"])
    target = state.get("target") or 0
    runs_needed = state.get("runs_needed") or 0
    required_rr = state.get("required_run_rate") or 0.0
    current_rr = state["current_run_rate"]

    row = {
        "innings": innings,
        "score": state["score"],
        "wickets": state["wickets"],
        "overs_completed": state["overs_completed"],
        "balls_remaining": state["balls_remaining"],
        "wickets_left": state["wickets_left"],
        "current_run_rate": current_rr,
        "target_or_zero": target if target else 0,
        "runs_needed_or_zero": runs_needed if runs_needed > 0 else 0,
        "required_run_rate_or_zero": required_rr if innings == 2 else 0.0,
        "run_rate_diff": (current_rr - required_rr) if innings == 2 else 0.0,
    }
    row.update(_phase_flags(over))
    return row


def to_feature_matrix(rows: List[dict]) -> pd.DataFrame:
    df = pd.DataFrame([build_features_row(r) for r in rows])
    return df[FEATURE_COLUMNS]
