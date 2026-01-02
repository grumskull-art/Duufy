from __future__ import annotations

from ai_parser_contract import (
    PARSE_RESULT_ADAPTER,
    ParsedItem,
    ParseResult,
    fallback_parse,
)


def should_use_ai(raw: str, force_ai: bool = False) -> bool:
    if force_ai:
        return True
    if not raw or not raw.strip():
        return True
    tokens = [token for token in raw.split() if token]
    return len(tokens) < 3


def ai_parse_stub(raw: str) -> ParseResult:
    raise NotImplementedError("AI parser not wired yet")


def parse_input(raw: str, *, force_ai: bool = False) -> ParseResult:
    if should_use_ai(raw, force_ai=force_ai):
        try:
            result = ai_parse_stub(raw)
        except NotImplementedError:
            raise
        except Exception:
            result = fallback_parse(raw)
            result.warnings.append("AI_FAILED")
        return PARSE_RESULT_ADAPTER.validate_python(result)

    result = fallback_parse(raw)
    return PARSE_RESULT_ADAPTER.validate_python(result)
