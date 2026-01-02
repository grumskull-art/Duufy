import importlib
import os
from typing import Callable


def is_ai_enabled() -> bool:
    value = os.getenv("DUUFY_AI_ENABLED", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _not_implemented(_: str) -> object:
    raise NotImplementedError("AI provider not wired yet")


def get_ai_parser() -> Callable[[str], object]:
    if not is_ai_enabled():
        raise RuntimeError("AI_DISABLED")

    try:
        provider = importlib.import_module("ai_provider_placeholder")
        parser = getattr(provider, "parse", None)
    except Exception:
        return _not_implemented

    if not callable(parser):
        return _not_implemented

    return parser
