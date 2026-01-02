from __future__ import annotations

from ai_provider import get_ai_parser
from ai_parser_ai_contract import AIParsePayload, validate_ai_payload
from ai_parser_contract import (
    PARSE_RESULT_ADAPTER,
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


def _ai_payload_to_parse_result(payload: AIParsePayload) -> ParseResult:
    item_confidence = min(max(payload.confidence, 0.0), 1.0)
    items = []
    for item in payload.items:
        name = item.get("name", "")
        if not isinstance(name, str):
            name = ""
        name = name.strip()
        if not name:
            continue
        quantity = item.get("quantity")
        if quantity is not None and not isinstance(quantity, str):
            quantity = None
        category = item.get("category")
        if category is not None and not isinstance(category, str):
            category = None
        items.append(
            {
                "name": name,
                "quantity": quantity,
                "category": category,
                "confidence": item_confidence,
            }
        )
    warnings = ["LOW_CONFIDENCE"] if item_confidence < 0.5 else []
    return ParseResult(items=items, source="ai", warnings=warnings)


def ai_parse_stub(raw: str) -> object:
    # Placeholder for future AI parser integration.
    raise NotImplementedError("AI parser not wired yet")


def parse_input(raw: str, *, force_ai: bool = False) -> ParseResult:
    if should_use_ai(raw, force_ai=force_ai):
        try:
            parser = get_ai_parser()
            result = parser(raw)
        except RuntimeError as exc:
            if str(exc) != "AI_DISABLED":
                raise
            result = fallback_parse(raw)
            result.warnings.append("AI_DISABLED")
            return PARSE_RESULT_ADAPTER.validate_python(result)
        except NotImplementedError:
            raise
        except Exception:
            result = fallback_parse(raw)
            result.warnings.append("AI_FAILED")
            return PARSE_RESULT_ADAPTER.validate_python(result)
        if isinstance(result, ParseResult):
            return PARSE_RESULT_ADAPTER.validate_python(result)
        payload = validate_ai_payload(result)
        converted = _ai_payload_to_parse_result(payload)
        return PARSE_RESULT_ADAPTER.validate_python(converted)

    result = fallback_parse(raw)
    return PARSE_RESULT_ADAPTER.validate_python(result)
