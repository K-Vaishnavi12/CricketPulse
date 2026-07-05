"""Stream a simulated live IPL match into Kafka topic `balls.raw`.

Usage:
    python -m src.producer.match_producer
    python -m src.producer.match_producer --team-a "Bengaluru Blazers" --team-b "Kolkata Kings" --interval 0.5
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Optional

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from tenacity import retry, stop_after_attempt, wait_fixed

from src.common.config import settings
from src.common.logging import get_logger
from src.simulator.match_engine import MatchSimulator

log = get_logger("producer")


@retry(stop=stop_after_attempt(10), wait=wait_fixed(3), reraise=True)
def _connect() -> KafkaProducer:
    log.info(f"Connecting to Kafka at {settings.kafka_bootstrap_servers}")
    return KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        linger_ms=10,
        retries=3,
    )


def stream_match(team_a: str, team_b: str, venue: str,
                 interval: float, seed: Optional[int]) -> None:
    producer = _connect()

    sim = MatchSimulator(team_a_name=team_a, team_b_name=team_b, venue=venue, seed=seed)
    log.info(f"Match {sim.meta.match_id}: {team_a} vs {team_b} @ {venue}")
    log.info(f"Toss: {sim.meta.toss_winner} chose to {sim.meta.toss_decision}")

    # first, send a meta message on a control key so consumers know match started
    producer.send(
        settings.kafka_topic_balls,
        key=sim.meta.match_id,
        value={
            "type": "match_start",
            "match_id": sim.meta.match_id,
            "team_a": sim.meta.team_a,
            "team_b": sim.meta.team_b,
            "venue": sim.meta.venue,
            "toss_winner": sim.meta.toss_winner,
            "toss_decision": sim.meta.toss_decision,
            "start_ts": sim.meta.start_ts.isoformat(),
        },
    )
    producer.flush()

    ball_count = 0
    for ball in sim.stream_balls():
        payload = ball.model_dump(mode="json")
        payload["type"] = "ball"
        producer.send(
            settings.kafka_topic_balls,
            key=ball.match_id,
            value=payload,
        )
        ball_count += 1

        if ball_count % 6 == 0:
            producer.flush()
            log.info(
                f"Over {ball.over}.{ball.ball} | I{ball.innings} | "
                f"{ball.batting_team[:3].upper()} {ball.innings_score}/{ball.innings_wickets}"
                f"{' | target ' + str(ball.target) if ball.target else ''}"
            )

        time.sleep(interval)

    # end of match
    producer.send(
        settings.kafka_topic_balls,
        key=sim.meta.match_id,
        value={
            "type": "match_end",
            "match_id": sim.meta.match_id,
            "winner": sim.state.winner,
            "result_text": sim.state.result_text,
        },
    )
    producer.flush()
    producer.close()
    log.success(f"Match finished. Result: {sim.state.result_text}")
    log.info(f"Sent {ball_count} ball events to topic '{settings.kafka_topic_balls}'")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-a", default=settings.team_a)
    parser.add_argument("--team-b", default=settings.team_b)
    parser.add_argument("--venue", default=settings.venue)
    parser.add_argument("--interval", type=float, default=settings.ball_interval_seconds,
                        help="Seconds between balls")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    args = parser.parse_args()

    try:
        stream_match(args.team_a, args.team_b, args.venue, args.interval, args.seed)
    except NoBrokersAvailable:
        log.error("Kafka is not reachable. Is Docker Compose running?")
        log.error("  docker compose -f docker/docker-compose.yml up -d")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
