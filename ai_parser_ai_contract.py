from __future__ import annotations

from pydantic import BaseModel, Field, TypeAdapter


class AIParsePayload(BaseModel):
    items: list[dict]
    confidence: float = Field(ge=0.0, le=1.0)


_AI_PARSE_ADAPTER = TypeAdapter(AIParsePayload)


def validate_ai_payload(payload: object) -> AIParsePayload:
    return _AI_PARSE_ADAPTER.validate_python(payload)
