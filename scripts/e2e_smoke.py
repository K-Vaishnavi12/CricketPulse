"""End-to-end smoke test WITHOUT Kafka - useful for CI or a first sanity check.

Runs one simulated match straight into DuckDB + generates predictions + refreshes gold.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.common.logging import get_logger
from src.consumer.state import LiveMatchState
from src.ml.inference import RealTimePredictor
from src.simulator.match_engine import MatchSimulator
from src.warehouse.db import get_conn, init_schema, run_transformations

log = get_logger("e2e_smoke")


def main() -> None:
    log.info("Initializing schema...")
    init_schema()

    try:
        predictor = RealTimePredictor.load()
        log.info("Loaded ML models.")
    except FileNotFoundError:
        log.error("Models not trained. Run: python scripts/bootstrap.py")
        raise SystemExit(1)

    sim = MatchSimulator("Mumbai Mavericks", "Chennai Chargers", "Wankhede", seed=7)
    tracker = LiveMatchState()
    tracker.register_match(sim.meta.match_id, sim.meta.team_a, sim.meta.team_b)

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO bronze.matches_raw
                (match_id, team_a, team_b, venue, toss_winner, toss_decision, start_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (match_id) DO NOTHING
        """, [sim.meta.match_id, sim.meta.team_a, sim.meta.team_b, sim.meta.venue,
              sim.meta.toss_winner, sim.meta.toss_decision, sim.meta.start_ts])

    log.info(f"Simulating match {sim.meta.match_id}...")
    n_balls = 0
    for ball in sim.stream_balls():
        payload = ball.model_dump(mode="json")
        with get_conn() as conn:
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

        feats = tracker.feature_vector(payload["match_id"])
        if feats is not None:
            p_a = predictor.predict_win_prob_team_a(feats)
            fs = predictor.predict_final_score(feats, payload)
            with get_conn() as conn:
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
        n_balls += 1

    with get_conn() as conn:
        conn.execute("""
            UPDATE bronze.matches_raw
               SET winner=?, result_text=?, end_ts=CURRENT_TIMESTAMP
             WHERE match_id=?
        """, [sim.state.winner, sim.state.result_text, sim.meta.match_id])

    log.info("Running silver/gold transformations...")
    run_transformations()

    log.success(f"E2E smoke test passed. {n_balls} balls processed.")
    log.success(f"Match result: {sim.state.result_text}")
    log.info("You can now run:  streamlit run src/dashboard/app.py")


if __name__ == "__main__":
    main()
