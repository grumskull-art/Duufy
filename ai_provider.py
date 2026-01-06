import importlib
import os
from typing import Callable

from ai_config import load_ai_config

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

_client = None


def get_client():
    global _client
    if Anthropic is None:
        raise RuntimeError("ANTHROPIC_NOT_AVAILABLE")
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def is_ai_enabled() -> bool:
    value = os.getenv("DUUFY_AI_ENABLED", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _not_implemented(_: str) -> object:
    raise NotImplementedError("AI provider not wired yet")


def get_ai_parser() -> Callable[[str], object]:
    config = load_ai_config()
    if not config.enabled:
        raise RuntimeError("AI_DISABLED")

    try:
        provider = importlib.import_module("ai_provider_placeholder")
        parser = getattr(provider, "parse", None)
    except Exception:
        return _not_implemented

    if not callable(parser):
        return _not_implemented

    return parser
