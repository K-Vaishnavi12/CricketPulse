"""Generate a large synthetic dataset by simulating many matches, then train:

    1. Win-probability classifier (batting team wins from this ball state)
    2. Final-score regressor (predicts innings final total from mid-innings state)

Both are simple scikit-learn models. The classifier is calibrated so probabilities
look sensible on the dashboard.

Usage:
    python -m src.ml.train --matches 300
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.common.config import settings
from src.common.logging import get_logger
from src.ml.features import FEATURE_COLUMNS, build_features_row
from src.simulator.match_engine import MatchSimulator

log = get_logger("ml.train")


TEAM_POOL = [
    "Mumbai Mavericks", "Chennai Chargers", "Bengaluru Blazers", "Kolkata Kings",
    "Delhi Dynamos", "Hyderabad Hawks", "Rajasthan Royals", "Punjab Panthers",
    "Lucknow Lions", "Gujarat Giants",
]
VENUE_POOL = ["Wankhede", "Chinnaswamy", "Eden Gardens", "Chepauk", "Kotla"]


def _simulate_and_label(n_matches: int, seed: int = 0) -> pd.DataFrame:
    """Simulate n_matches; produce one row per ball with the true match outcome."""
    rng = np.random.default_rng(seed)
    all_rows: List[dict] = []

    for i in range(n_matches):
        t_a, t_b = rng.choice(TEAM_POOL, size=2, replace=False)
        venue = rng.choice(VENUE_POOL)
        sim = MatchSimulator(t_a, t_b, venue, seed=int(rng.integers(0, 1_000_000)))
        balls = list(sim.stream_balls())
        if not balls or sim.state.winner is None:
            continue

        # figure out per-innings final for regressor labels
        inn_finals = {}
        for b in balls:
            inn_finals[b.innings] = b.innings_score  # last value wins

        for b in balls:
            batting = b.batting_team
            batter_won = int(sim.state.winner == batting)
            balls_bowled = int(round(b.innings_overs_completed * 6))
            balls_remaining = max(0, 120 - balls_bowled)
            wickets_left = 10 - b.innings_wickets
            current_rr = (b.innings_score / b.innings_overs_completed) if b.innings_overs_completed > 0 else 0.0

            state = {
                "innings": b.innings,
                "score": b.innings_score,
                "wickets": b.innings_wickets,
                "overs_completed": b.innings_overs_completed,
                "balls_remaining": balls_remaining,
                "wickets_left": wickets_left,
                "current_run_rate": current_rr,
                "target": b.target,
                "runs_needed": (b.target - b.innings_score) if b.target else None,
                "required_run_rate": (
                    ((b.target - b.innings_score) * 6.0 / balls_remaining)
                    if b.target and balls_remaining > 0 else None
                ),
            }
            row = build_features_row(state)
            row["label_win"] = batter_won
            row["label_final_score"] = inn_finals[b.innings]
            all_rows.append(row)

    return pd.DataFrame(all_rows)


def train(n_matches: int = 300, test_frac: float = 0.2) -> None:
    log.info(f"Simulating {n_matches} matches to build training set...")
    df = _simulate_and_label(n_matches)
    log.info(f"Generated {len(df):,} ball rows.")

    X = df[FEATURE_COLUMNS]
    y_win = df["label_win"]
    y_score = df["label_final_score"]

    X_tr, X_te, y_tr, y_te, s_tr, s_te = train_test_split(
        X, y_win, y_score, test_size=test_frac, random_state=42, stratify=y_win
    )

    # ----------- Win-probability classifier -----------
    log.info("Training win-probability classifier (GradientBoosting)...")
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("gb", GradientBoostingClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.08, random_state=42,
        )),
    ])
    clf.fit(X_tr, y_tr)
    p_te = clf.predict_proba(X_te)[:, 1]
    log.info(f"  log-loss   : {log_loss(y_te, p_te):.4f}")
    log.info(f"  brier      : {brier_score_loss(y_te, p_te):.4f}")
    log.info(f"  accuracy@50: {(p_te.round() == y_te).mean():.3f}")

    # ----------- Final-score regressor -----------
    log.info("Training final-score regressor (GradientBoosting)...")
    reg = Pipeline([
        ("scaler", StandardScaler()),
        ("gb", GradientBoostingRegressor(
            n_estimators=250, max_depth=4, learning_rate=0.08, random_state=42,
        )),
    ])
    reg.fit(X_tr, s_tr)
    s_pred = reg.predict(X_te)
    log.info(f"  MAE (runs) : {mean_absolute_error(s_te, s_pred):.2f}")

    # ----------- Persist -----------
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    clf_path = settings.models_dir / "win_prob_model.pkl"
    reg_path = settings.models_dir / "final_score_model.pkl"
    joblib.dump(clf, clf_path)
    joblib.dump(reg, reg_path)
    log.success(f"Saved classifier -> {clf_path}")
    log.success(f"Saved regressor  -> {reg_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=300)
    args = parser.parse_args()
    train(args.matches)


if __name__ == "__main__":
    main()
