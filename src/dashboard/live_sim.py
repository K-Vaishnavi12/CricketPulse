"""In-browser live match streamer for Streamlit Cloud demos.

On Streamlit Cloud there's no Kafka/Airflow/consumer running. Instead, we can
run the simulator + inference + warehouse writes directly inside the streamlit
process, one ball at a time, using session state as a coroutine driver.

Usage from the dashboard:
    from src.dashboard.live_sim import step_live_match, start_new_match
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator, Optional

import streamlit as st

from src.common.logging import get_logger
from src.consumer.state import LiveMatchState
from src.ml.inference import RealTimePredictor
from src.simulator.match_engine import MatchSimulator
from src.warehouse.db import get_conn, init_schema, run_transformations

log = get_logger("dashboard.live_sim")


@st.cache_resource
def _load_predictor() -> Optional[RealTimePredictor]:
    try:
        return RealTimePredictor.load()
    except FileNotFoundError:
        return None


def _ensure_schema() -> None:
    init_schema()


def start_new_match(team_a: str, team_b: str, venue: str, seed: Optional[int] = None) -> str:
    """Kick off a new match. Returns the new match_id."""
    _ensure_schema()

    sim = MatchSimulator(team_a, team_b, venue, seed=seed)
    st.session_state.live_sim = sim
    st.session_state.live_iter = sim.stream_balls()
    st.session_state.live_tracker = LiveMatchState()
    st.session_state.live_tracker.register_match(sim.meta.match_id, sim.meta.team_a, sim.meta.team_b)
    st.session_state.live_match_id = sim.meta.match_id
    st.session_state.live_balls_delivered = 0
    st.session_state.live_finished = False

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO bronze.matches_raw
                (match_id, team_a, team_b, venue, toss_winner, toss_decision, start_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (match_id) DO NOTHING
        """, [sim.meta.match_id, sim.meta.team_a, sim.meta.team_b, sim.meta.venue,
              sim.meta.toss_winner, sim.meta.toss_decision, sim.meta.start_ts])

    return sim.meta.match_id


def is_live_active() -> bool:
    return "live_iter" in st.session_state and not st.session_state.get("live_finished", False)


def step_live_match(balls_per_tick: int = 3) -> int:
    """Consume `balls_per_tick` balls from the live iterator, write to DB + predict.

    Returns number of balls actually processed this tick (0 if finished).
    """
    if not is_live_active():
        return 0

    iterator: Iterator = st.session_state.live_iter
    tracker: LiveMatchState = st.session_state.live_tracker
    predictor = _load_predictor()
    match_id = st.session_state.live_match_id

    processed = 0
    with get_conn() as conn:
        for _ in range(balls_per_tick):
            try:
                ball = next(iterator)
            except StopIteration:
                st.session_state.live_finished = True
                # finalize match record
                sim: MatchSimulator = st.session_state.live_sim
                conn.execute("""
                    UPDATE bronze.matches_raw
                       SET winner=?, result_text=?, end_ts=CURRENT_TIMESTAMP
                     WHERE match_id=?
                """, [sim.state.winner, sim.state.result_text, match_id])
                break

            payload = ball.model_dump(mode="json")
            conn.execute("""
                INSERT INTO bronze.balls_raw (
                    match_id, innings, over, ball, batting_team, bowling_team,
                    batter, non_striker, bowler, runs_batter, runs_extras,
                    extras_kind, is_wicket, dismissal_kind, player_out,
                    innings_score, innings_wickets, innings_overs_completed,
                    target, event_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                payload["match_id"], payload["innings"], payload["over"], payload["ball"],
                payload["batting_team"], payload["bowling_team"],
                payload["batter"], payload["non_striker"], payload["bowler"],
                payload["runs_batter"], payload["runs_extras"], payload.get("extras_kind"),
                payload["is_wicket"], payload.get("dismissal_kind"), payload.get("player_out"),
                payload["innings_score"], payload["innings_wickets"], payload["innings_overs_completed"],
                payload.get("target"), payload["event_ts"],
            ])
            tracker.update_from_ball(payload)

            if predictor is not None:
                feats = tracker.feature_vector(payload["match_id"])
                if feats is not None:
                    try:
                        p_a = predictor.predict_win_prob_team_a(feats)
                        fs = predictor.predict_final_score(feats, payload)
                        conn.execute("""
                            INSERT INTO bronze.predictions_raw
                                (match_id, innings, over, ball, win_prob_team_a,
                                 win_prob_team_b, predicted_final_score, event_ts)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, [
                            payload["match_id"], payload["innings"], payload["over"], payload["ball"],
                            float(p_a), 1.0 - float(p_a), fs,
                            datetime.now(timezone.utc),
                        ])
                    except Exception as e:
                        log.warning(f"Inference failed: {e}")

            processed += 1
            st.session_state.live_balls_delivered = st.session_state.get("live_balls_delivered", 0) + 1

    # refresh gold layer occasionally so scorecards update
    if st.session_state.get("live_balls_delivered", 0) % 6 == 0:
        try:
            run_transformations()
        except Exception as e:
            log.warning(f"Transformation failed: {e}")

    return processed


def stop_live_match() -> None:
    for k in ("live_sim", "live_iter", "live_tracker", "live_match_id",
              "live_balls_delivered", "live_finished"):
        st.session_state.pop(k, None)


def live_status() -> dict:
    return {
        "active": is_live_active(),
        "match_id": st.session_state.get("live_match_id"),
        "balls_delivered": st.session_state.get("live_balls_delivered", 0),
        "finished": st.session_state.get("live_finished", False),
    }
