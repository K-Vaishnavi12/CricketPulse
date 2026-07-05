"""Consume balls from Kafka -> land in bronze -> predict -> publish predictions.

Runs continuously; safe to Ctrl+C.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
from tenacity import retry, stop_after_attempt, wait_fixed

from src.common.config import settings
from src.common.logging import get_logger
from src.consumer.state import LiveMatchState
from src.ml.inference import RealTimePredictor
from src.warehouse.db import get_conn, init_schema, run_transformations

log = get_logger("consumer")


@retry(stop=stop_after_attempt(10), wait=wait_fixed(3), reraise=True)
def _connect_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        settings.kafka_topic_balls,
        bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
        group_id=settings.kafka_consumer_group,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )


@retry(stop=stop_after_attempt(10), wait=wait_fixed(3), reraise=True)
def _connect_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )


def _insert_match_start(payload: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO bronze.matches_raw
                (match_id, team_a, team_b, venue, toss_winner, toss_decision, start_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (match_id) DO NOTHING
        """, [
            payload["match_id"], payload["team_a"], payload["team_b"],
            payload["venue"], payload["toss_winner"], payload["toss_decision"],
            payload["start_ts"],
        ])


def _insert_match_end(payload: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            UPDATE bronze.matches_raw
               SET winner = ?, result_text = ?, end_ts = CURRENT_TIMESTAMP
             WHERE match_id = ?
        """, [payload.get("winner"), payload.get("result_text"), payload["match_id"]])


def _insert_ball(payload: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO bronze.balls_raw (
                match_id, innings, over, ball,
                batting_team, bowling_team,
                batter, non_striker, bowler,
                runs_batter, runs_extras, extras_kind,
                is_wicket, dismissal_kind, player_out,
                innings_score, innings_wickets, innings_overs_completed,
                target, event_ts
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?
            )
        """, [
            payload["match_id"], payload["innings"], payload["over"], payload["ball"],
            payload["batting_team"], payload["bowling_team"],
            payload["batter"], payload["non_striker"], payload["bowler"],
            payload["runs_batter"], payload["runs_extras"], payload.get("extras_kind"),
            payload["is_wicket"], payload.get("dismissal_kind"), payload.get("player_out"),
            payload["innings_score"], payload["innings_wickets"], payload["innings_overs_completed"],
            payload.get("target"), payload["event_ts"],
        ])


def _insert_prediction(pred: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO bronze.predictions_raw
                (match_id, innings, over, ball,
                 win_prob_team_a, win_prob_team_b, predicted_final_score, event_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            pred["match_id"], pred["innings"], pred["over"], pred["ball"],
            pred["win_prob_team_a"], pred["win_prob_team_b"],
            pred.get("predicted_final_score"), pred["event_ts"],
        ])


def run() -> None:
    log.info("Initializing warehouse schema...")
    init_schema()

    log.info("Loading ML model...")
    try:
        predictor: Optional[RealTimePredictor] = RealTimePredictor.load()
        log.info("Win-probability model loaded.")
    except FileNotFoundError:
        predictor = None
        log.warning("No ML model found. Run: python scripts/bootstrap.py")

    match_state = LiveMatchState()

    log.info(f"Connecting to Kafka topic '{settings.kafka_topic_balls}'...")
    consumer = _connect_consumer()
    producer = _connect_producer()
    log.success("Consumer running. Waiting for balls...")

    ball_count = 0
    try:
        for msg in consumer:
            payload = msg.value
            msg_type = payload.get("type", "ball")

            if msg_type == "match_start":
                _insert_match_start(payload)
                match_state.register_match(
                    match_id=payload["match_id"],
                    team_a=payload["team_a"],
                    team_b=payload["team_b"],
                )
                log.info(f"Match started: {payload['team_a']} vs {payload['team_b']}")
                continue

            if msg_type == "match_end":
                _insert_match_end(payload)
                run_transformations()
                log.success(f"Match ended: {payload.get('result_text')}")
                continue

            # regular ball event
            _insert_ball(payload)
            ball_count += 1
            match_state.update_from_ball(payload)

            # real-time inference
            if predictor is not None:
                try:
                    feats = match_state.feature_vector(payload["match_id"])
                    if feats is not None:
                        prob_a = predictor.predict_win_prob_team_a(feats)
                        prob_b = 1.0 - prob_a
                        predicted_final = predictor.predict_final_score(feats, payload)

                        pred = {
                            "match_id": payload["match_id"],
                            "innings": payload["innings"],
                            "over": payload["over"],
                            "ball": payload["ball"],
                            "win_prob_team_a": round(float(prob_a), 4),
                            "win_prob_team_b": round(float(prob_b), 4),
                            "predicted_final_score": predicted_final,
                            "event_ts": datetime.now(timezone.utc).isoformat(),
                        }
                        _insert_prediction(pred)
                        producer.send(settings.kafka_topic_predictions,
                                      key=payload["match_id"], value=pred)
                except Exception as e:
                    log.warning(f"Prediction failed: {e}")

            # transform every 6 balls so the dashboard sees fresh aggregates
            if ball_count % 6 == 0:
                run_transformations()
                producer.flush()
                log.info(
                    f"[{ball_count} balls] O{payload['over']}.{payload['ball']} I{payload['innings']} "
                    f"{payload['batting_team'][:3].upper()} {payload['innings_score']}/{payload['innings_wickets']}"
                )

    except KeyboardInterrupt:
        log.info("Consumer stopped by user.")
    finally:
        consumer.close()
        producer.close()


def main() -> None:
    try:
        run()
    except NoBrokersAvailable:
        log.error("Kafka is not reachable. Is Docker Compose running?")
        log.error("  docker compose -f docker/docker-compose.yml up -d")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
