"""Central config, loaded from environment variables (.env) or Streamlit secrets."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


def _hydrate_from_streamlit_secrets() -> None:
    """On Streamlit Cloud, secrets come from st.secrets. Push them into os.environ
    so pydantic-settings picks them up transparently."""
    try:
        import streamlit as st  # type: ignore
        secrets = dict(st.secrets)  # will raise if not on Streamlit
        for k, v in secrets.items():
            # Only set if not already in the env
            os.environ.setdefault(k.upper(), str(v))
    except Exception:
        # Not running under Streamlit or secrets not configured. That's fine.
        pass


_hydrate_from_streamlit_secrets()


class Settings(BaseSettings):
    # GenAI
    gemini_api_key: str = "not-set"
    gemini_model: str = "gemini-2.0-flash-lite"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_balls: str = "balls.raw"
    kafka_topic_predictions: str = "balls.predictions"
    kafka_consumer_group: str = "cricketpulse-consumer"

    # Warehouse
    duckdb_path: str = "data/warehouse/cricketpulse.duckdb"

    # Simulation
    ball_interval_seconds: float = 1.5
    team_a: str = "Mumbai Mavericks"
    team_b: str = "Chennai Chargers"
    venue: str = "Wankhede Stadium"

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def duckdb_absolute_path(self) -> Path:
        p = Path(self.duckdb_path)
        if not p.is_absolute():
            p = ROOT_DIR / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_dir(self) -> Path:
        d = ROOT_DIR / "models"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()
