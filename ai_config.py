from __future__ import annotations

import os

from pydantic import BaseModel, Field


class AIConfig(BaseModel):
    enabled: bool = False
    timeout_seconds: int = Field(default=30, ge=1)
    max_tokens: int = Field(default=512, ge=1)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def load_ai_config() -> AIConfig:
    data: dict[str, object] = {}

    enabled = os.getenv("DUUFY_AI_ENABLED")
    if enabled is not None:
        data["enabled"] = enabled.strip().lower() in {"1", "true", "yes"}

    timeout_seconds = os.getenv("DUUFY_AI_TIMEOUT")
    if timeout_seconds is not None:
        data["timeout_seconds"] = int(timeout_seconds)

    max_tokens = os.getenv("DUUFY_AI_MAX_TOKENS")
    if max_tokens is not None:
        data["max_tokens"] = int(max_tokens)

    min_confidence = os.getenv("DUUFY_AI_MIN_CONFIDENCE")
    if min_confidence is not None:
        data["min_confidence"] = float(min_confidence)

    return AIConfig(**data)
