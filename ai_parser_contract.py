from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter


class ParsedItem(BaseModel):
    name: str = Field(min_length=1)
    quantity: str | None = None
    category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class ParseResult(BaseModel):
    items: list[ParsedItem]
    source: Literal["fallback", "ai"]
    warnings: list[str] = Field(default_factory=list)


PARSE_RESULT_ADAPTER = TypeAdapter(ParseResult)


def fallback_parse(raw: str) -> ParseResult:
    if not raw or not raw.strip():
        return ParseResult(
            items=[],
            source="fallback",
            warnings=["EMPTY_INPUT"],
        )

    parts = [part.strip() for part in raw.replace("\n", ",").split(",")]
    items = [
        ParsedItem(
            name=part,
            quantity=None,
            category=None,
            confidence=0.3,
        )
        for part in parts
        if part
    ]

    warnings: list[str] = []
    if not items:
        warnings.append("NO_TOKENS_AFTER_SPLIT")

    return ParseResult(items=items, source="fallback", warnings=warnings)
