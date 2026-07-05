"""Loguru logger with sensible defaults."""
from __future__ import annotations

import sys

from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level:<8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    colorize=True,
)


def get_logger(name: str):
    return logger.bind(module=name)
