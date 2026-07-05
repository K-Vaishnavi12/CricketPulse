"""One-shot bootstrap: warehouse schema + train ML models.

Run this ONCE before starting the pipeline:
    python scripts/bootstrap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# add repo root to path so `src.` imports work when running as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.common.logging import get_logger
from src.ml.train import train
from src.warehouse.db import init_schema

log = get_logger("bootstrap")


def main() -> None:
    log.info("Step 1/2: creating DuckDB warehouse schema...")
    init_schema()
    log.success("Schema ready.")

    log.info("Step 2/2: training ML models on 300 simulated matches...")
    log.info("(This takes ~1-2 minutes. Grab water.)")
    train(n_matches=300)
    log.success("Models trained and saved to models/*.pkl")

    log.info("")
    log.success("Bootstrap complete! Next steps:")
    log.info("  1. Start Docker infra:")
    log.info("     docker compose -f docker/docker-compose.yml up -d")
    log.info("  2. In three separate terminals:")
    log.info("     python -m src.producer.match_producer")
    log.info("     python -m src.consumer.ball_consumer")
    log.info("     streamlit run src/dashboard/app.py")


if __name__ == "__main__":
    main()
