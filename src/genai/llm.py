"""Gemini LLM factory with quota-aware wrappers + graceful degradation."""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, Callable, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from src.common.config import settings
from src.common.logging import get_logger

log = get_logger("genai.llm")


# Module-level quota tracking (survives across calls in the same process)
_QUOTA_STATE: dict[str, Any] = {
    "exhausted_until": 0.0,   # unix ts when we can try again
    "call_count_session": 0,  # total calls this Streamlit session
    "last_error": None,
}


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    if not settings.gemini_api_key or settings.gemini_api_key == "not-set":
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Get a free key at https://aistudio.google.com/apikey and set it in .env"
        )
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
        max_output_tokens=1024,
        convert_system_message_to_human=True,
    )


def is_configured() -> bool:
    return bool(settings.gemini_api_key) and settings.gemini_api_key != "not-set"


def quota_available() -> bool:
    """Return False if we know the quota is exhausted until some future time."""
    return time.time() >= _QUOTA_STATE["exhausted_until"]


def quota_seconds_remaining() -> int:
    """How many seconds until quota is expected to be usable again."""
    return max(0, int(_QUOTA_STATE["exhausted_until"] - time.time()))


def call_with_fallback(fn: Callable[[], str], fallback: str = "") -> str:
    """Call a Gemini-invoking function; on quota or transient errors, return `fallback`.

    Also records quota state so subsequent calls skip the API entirely for a while.
    """
    if not is_configured():
        return fallback
    if not quota_available():
        log.debug(f"Skipping Gemini call (quota cooldown, {quota_seconds_remaining()}s remaining)")
        return fallback
    try:
        result = fn()
        _QUOTA_STATE["call_count_session"] += 1
        _QUOTA_STATE["last_error"] = None
        return result
    except Exception as e:
        msg = str(e)
        _QUOTA_STATE["last_error"] = msg
        # Detect Google's 429 quota errors
        if any(sig in msg.lower() for sig in ("429", "quota", "resource_exhausted", "rate limit")):
            # be conservative: assume we can't call again for 60 seconds
            _QUOTA_STATE["exhausted_until"] = time.time() + 60
            log.warning(f"Gemini quota hit. Backing off 60s. ({msg[:120]})")
        else:
            log.warning(f"Gemini call failed: {msg[:200]}")
        return fallback


def quota_status() -> dict:
    """For the sidebar UI."""
    return {
        "configured": is_configured(),
        "available": quota_available(),
        "cooldown_s": quota_seconds_remaining(),
        "calls_this_session": _QUOTA_STATE["call_count_session"],
        "last_error": _QUOTA_STATE["last_error"],
    }
