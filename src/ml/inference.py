"""Real-time inference: loads .pkl models and scores one ball at a time."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import joblib
import pandas as pd

from src.common.config import settings
from src.ml.features import FEATURE_COLUMNS, build_features_row


@dataclass
class RealTimePredictor:
    win_clf: object
    score_reg: object

    @classmethod
    def load(cls) -> "RealTimePredictor":
        clf_path = settings.models_dir / "win_prob_model.pkl"
        reg_path = settings.models_dir / "final_score_model.pkl"
        if not clf_path.exists():
            raise FileNotFoundError(f"{clf_path} not found. Run: python -m src.ml.train")
        return cls(
            win_clf=joblib.load(clf_path),
            score_reg=joblib.load(reg_path),
        )

    def _row(self, state: dict) -> pd.DataFrame:
        row = build_features_row(state)
        return pd.DataFrame([row])[FEATURE_COLUMNS]

    def predict_win_prob_team_a(self, state: dict) -> float:
        """Return the probability that TEAM A (as defined at match creation) wins."""
        X = self._row(state)
        # model outputs P(batting team wins); flip if team A isn't batting
        p_batting_wins = float(self.win_clf.predict_proba(X)[0, 1])
        if state["batting_team"] == state["team_a"]:
            return p_batting_wins
        return 1.0 - p_batting_wins

    def predict_final_score(self, state: dict, ball_payload: Optional[dict] = None) -> Optional[int]:
        """Predict this innings' final total. In innings 2, cap at target."""
        X = self._row(state)
        pred = float(self.score_reg.predict(X)[0])
        # sanity clamps
        pred = max(state["score"], pred)          # never go below current
        pred = min(pred, state["score"] + 20 * (state["balls_remaining"] / 6.0))  # cap upside
        if state.get("target"):
            pred = min(pred, state["target"] + 5)  # in innings 2, near the target
        return int(round(pred))
