"""Reusable Gemini LLM factory."""
from __future__ import annotations

from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from src.common.config import settings


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
