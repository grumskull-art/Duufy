"""State-of-the-art AI shopping list parser with fuzzy matching and async support."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from functools import lru_cache
from typing import Literal, TypedDict

# Optional dependencies
try:
    from anthropic import AsyncAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def _anthropic_available() -> bool:
    return False


Category = Literal[
    "mejeri",
    "kød",
    "fisk",
    "bager",
    "grønt",
    "frugt",
    "drikkevarer",
    "kolonial",
    "husholdning",
    "æg",
    "andet",
]
Confidence = Literal["high", "low", "none"]


class ParsedItem(TypedDict):
    item: str
    quantity: str
    category: Category
    image_url: str


class ParseResult(TypedDict):
    items: list[ParsedItem]
    method: Literal["local", "ai"]
    confidence: Confidence
    original_text: str
    used_alternative: str | None


# Immutable lookups (compile-time constants)
_CATEGORIES: dict[str, Category] = {
    "mælk": "mejeri",
    "letmælk": "mejeri",
    "minimælk": "mejeri",
    "sødmælk": "mejeri",
    "smør": "mejeri",
    "ost": "mejeri",
    "fløde": "mejeri",
    "piskefløde": "mejeri",
    "yoghurt": "mejeri",
    "skyr": "mejeri",
    "cremefraiche": "mejeri",
    "kærnemælk": "mejeri",
    "ymer": "mejeri",
    "mozzarella": "mejeri",
    "kylling": "kød",
    "oksekød": "kød",
    "hakket": "kød",
    "hakkekød": "kød",
    "svinekød": "kød",
    "bacon": "kød",
    "pølser": "kød",
    "hamburgerryg": "kød",
    "rullepølse": "kød",
    "leverpostej": "kød",
    "skinke": "kød",
    "medister": "kød",
    "kalvekød": "kød",
    "lammekød": "kød",
    "laks": "fisk",
    "tun": "fisk",
    "torsk": "fisk",
    "rejer": "fisk",
    "brød": "bager",
    "rugbrød": "bager",
    "franskbrød": "bager",
    "boller": "bager",
    "kartofler": "grønt",
    "kartoffel": "grønt",
    "løg": "grønt",
    "hvidløg": "grønt",
    "gulerødder": "grønt",
    "gulerod": "grønt",
    "tomater": "grønt",
    "tomat": "grønt",
    "agurk": "grønt",
    "salat": "grønt",
    "peberfrugt": "grønt",
    "broccoli": "grønt",
    "æbler": "frugt",
    "æble": "frugt",
    "bananer": "frugt",
    "banan": "frugt",
    "appelsiner": "frugt",
    "appelsin": "frugt",
    "pærer": "frugt",
    "citroner": "frugt",
    "juice": "drikkevarer",
    "cola": "drikkevarer",
    "sodavand": "drikkevarer",
    "øl": "drikkevarer",
    "vin": "drikkevarer",
    "vand": "drikkevarer",
    "kaffe": "drikkevarer",
    "te": "drikkevarer",
    "pasta": "kolonial",
    "ris": "kolonial",
    "mel": "kolonial",
    "sukker": "kolonial",
    "salt": "kolonial",
    "olie": "kolonial",
    "ketchup": "kolonial",
    "sennep": "kolonial",
    "mayonnaise": "kolonial",
    "remoulade": "kolonial",
    "toiletpapir": "husholdning",
    "køkkenrulle": "husholdning",
    "sæbe": "husholdning",
    "æg": "æg",
}

_DEFAULT_QTY: dict[str | Category, str] = {
    "mejeri": "1 L",
    "kød": "500 g",
    "fisk": "400 g",
    "bager": "1 stk",
    "grønt": "1 stk",
    "frugt": "1 stk",
    "drikkevarer": "1 L",
    "kolonial": "1 stk",
    "husholdning": "1 pk",
    "æg": "10 stk",
    "smør": "250 g",
    "ost": "400 g",
    "bacon": "1 pk",
    "pølser": "1 pk",
    "kartofler": "1 kg",
    "løg": "1 net",
    "æbler": "1 kg",
    "bananer": "1 bundt",
    "pasta": "500 g",
    "ris": "1 kg",
    "mel": "1 kg",
    "sukker": "1 kg",
}

_ALIASES: dict[str, str] = {
    "hambo": "hamburgerryg",
    "remu": "remoulade",
    "karto": "kartofler",
    "toma": "tomater",
    "gule": "gulerødder",
    "sømælk": "sødmælk",
    "smæølk": "sødmælk",
    "piskflø": "piskefløde",
    "rugbrø": "rugbrød",
    "franskbrø": "franskbrød",
    "lever": "leverpostej",
    "rulle": "rullepølse",
    "øllebørd": "øllebrød",
    "riberhus": "ost",
    "mellemlagret": "ost",
}

_WORD_TO_NUM: dict[str, str] = {
    "en": "1",
    "et": "1",
    "to": "2",
    "tre": "3",
    "fire": "4",
    "fem": "5",
    "seks": "6",
    "syv": "7",
    "otte": "8",
    "ni": "9",
    "ti": "10",
    "halvanden": "1.5",
    "halvandet": "1.5",
}

_KNOWN_PRODUCTS = tuple(_CATEGORIES.keys())

# Compiled regex patterns (initialized once)
_FILLER_PATTERNS = tuple(
    map(
        lambda p: re.compile(p, re.IGNORECASE),
        [
            r"^(øh|ehm|øhm|nå|nåh|altså|ikke|jo|bare|også)\s+",
            r"^(jeg skal have|vi skal have|skal have|jeg skal|vi skal)\s+",
            r"^(sku ha|sku have|ska ha|ska have)\s+",
            r"^(jeg|vi|man|den|det|de|der|den der|det der|de der)\s+",
            r"^(det der|ham der|hende der|den slags|du ved|jeg tænker)\s+",
            r"^(skal have|skal bruge|skal købe|mangler|vi mangler)\s+",
            r"^(noget|lidt|lidt af|lidt af det|nogen|nogle)\s+",
            r"^(tilføj|køb|hent|tag|skriv|sæt)\s+",
            r"^(en|et|den|det)\s+(?!liter|kilo|kg|l\s)",
        ],
    )
)

_AMOUNT_PATTERN = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(l|liter|ml|dl|cl|stk|stykker?|pakke|pakker|pk|poser?|g|gram|kg|kilo|fl|flaske|flasker|ds|dåse|dåser|bundt|net)?\s+",
    re.IGNORECASE,
)

_SPLIT_PATTERN = re.compile(
    r"\s+og\s+|\s*,\s*|\s+samt\s+|\s+plus\s+|\s+så\s+|\s+også\s+|\s+derefter\s+"
)
_ORDTAL_UNIT_PATTERN = re.compile(
    r"^(en|et|to|tre|fire|fem|seks|syv|otte|ni|ti|halvanden|halvandet)\s+(liter|l|kilo|kg|gram|g)\s+(.+)$",
    re.IGNORECASE,
)
_HALF_UNIT_PATTERN = re.compile(
    r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+(.+)$", re.IGNORECASE
)


@lru_cache(maxsize=512)
def _fuzzy_correct(word: str) -> str:
    """Fast fuzzy correction with caching and brand name removal."""
    lower = word.lower()

    # Remove common brand prefixes
    brand_prefixes = [
        "arla",
        "lurpak",
        "kims",
        "cocio",
        "riberhus",
        "knorr",
        "fjordland",
        "thise",
    ]
    words = lower.split()
    if len(words) > 1 and words[0] in brand_prefixes:
        lower = " ".join(words[1:])  # Remove brand, keep rest

    if alias := _ALIASES.get(lower):
        return alias
    if matches := get_close_matches(lower, _KNOWN_PRODUCTS, n=1, cutoff=0.7):
        return matches[0]
    return word


@lru_cache(maxsize=256)
def _get_category(item: str) -> Category:
    """Cached category lookup."""
    lower = item.lower()
    for key, cat in _CATEGORIES.items():
        if key in lower:
            return cat
    return "andet"


@lru_cache(maxsize=256)
def _get_default_qty(item: str) -> str:
    """Cached quantity lookup."""
    return "1"


def _clean_fillers(text: str) -> str:
    """Remove filler words efficiently from start AND middle of text."""
    text = text.lower().strip()

    # First pass: Remove from start (old behavior)
    for _ in range(3):
        old = text
        for pattern in _FILLER_PATTERNS:
            text = pattern.sub("", text)
        if text == old:
            break

    # Second pass: Remove mid-sentence fillers
    # Common phrases that appear in the middle
    mid_fillers = [
        r"\s+(så skal (jeg|vi) huske)\s+",
        r"\s+(jeg skal huske)\s+",
        r"\s+(skal huske)\s+",
        r"\s+(skal (jeg|vi) have)\s+",
        r"\s+(må ikke glemme)\s+",
        r"\s+(husk at få)\s+",
    ]

    for filler in mid_fillers:
        text = re.sub(filler, " ", text, flags=re.IGNORECASE)

    # Clean up multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _normalize_unit(unit: str) -> str:
    """Fast unit normalization."""
    u = unit.lower()
    return (
        "L"
        if u in ("l", "liter")
        else (
            "kg"
            if u in ("kg", "kilo")
            else (
                "g"
                if u in ("g", "gram")
                else (
                    "ml"
                    if u in ("ml", "milliliter")
                    else (
                        "dl"
                        if u in ("dl", "deciliter")
                        else (
                            "stk"
                            if u in ("stk", "stykker", "stykke")
                            else "pk" if u in ("pk", "pakke", "pakker") else unit
                        )
                    )
                )
            )
        )
    )


def local_parse(text: str) -> list[ParsedItem]:
    """Fast local regex parser with minimal allocations."""
    from image_service import get_image_url

    text = _clean_fillers(text)
    # Split by delimiters and product names
    parts = []
    for p in _SPLIT_PATTERN.split(text):
        p = p.strip()
        if len(p) >= 2:
            # Clean fillers from each part (handles "også ost" -> "ost")
            p = _clean_fillers(p)
            if len(p) < 2:
                continue

            # Check for repetitions
            words = p.split()
            if len(words) > 1 and len(set(w[:3] for w in words)) == 1:
                # Repetition like "smø smø smør" - take last
                parts.append(words[-1])
            else:
                # Keep full phrase - fuzzy matching will handle it
                parts.append(p)
        elif len(p) >= 2:
            parts.append(p)

    items: list[ParsedItem] = []
    seen: set[str] = set()

    for part in parts:
        quantity = ""
        item_name = part

        # Try patterns in order of frequency
        if match := _ORDTAL_UNIT_PATTERN.match(part):
            num, unit, item_name = match.groups()
            quantity = f"{
                _WORD_TO_NUM.get(
                    num.lower(),
                    num)} {
                _normalize_unit(unit)}"
        elif match := _HALF_UNIT_PATTERN.match(part):
            qty_word, unit, item_name = match.groups()
            num = "0.5" if qty_word.lower() in ("halv", "halvt") else "1"
            quantity = f"{num} {_normalize_unit(unit)}"
        elif part[0].isdigit() and (match := _AMOUNT_PATTERN.match(part)):
            num, unit = match.groups()
            quantity = f"{num} {_normalize_unit(unit or 'stk')}"
            item_name = part[match.end() :]

        item_name = _fuzzy_correct(item_name.strip())
        if not item_name:
            continue

        # Dedup check
        key = item_name.lower()
        if key in seen:
            continue
        seen.add(key)

        category = _get_category(item_name)
        items.append(
            {
                "item": item_name.capitalize(),
                "quantity": quantity or _get_default_qty(item_name),
                "category": category,
                "image_url": get_image_url(item_name, category),
            }
        )

    return items


async def ai_parse(text: str) -> list[ParsedItem]:
    """Async AI parsing with Claude."""
    if not _anthropic_available():
        return []

    if not (key := os.getenv("ANTHROPIC_API_KEY")):
        return []

    client = AsyncAnthropic(api_key=key)

    prompt = f"""Du parser utydelig dansk tale til JSON produkter.

FJERN: fyldord, gentagelser, mumlen
RET: stavefejl automatisk (sømælk→Sødmælk, hambo→Hamburgerryg)

Input: "{text}"
Output JSON array: [{{"item":"Produkt","quantity":"1 L","category":"mejeri","image_url":"/assets/images/produkt.jpg"}}]"""

    try:
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=600,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        parsed = json.loads(raw)
        return [
            item
            for item in parsed
            if all(k in item for k in ("item", "quantity", "category"))
        ]
    except Exception:
        return []


def smart_parse(text: str, force_ai: bool = False) -> ParseResult:
    """Synchronous entry point."""
    return asyncio.run(smart_parse_async(text, force_ai))


async def smart_parse_async(text: str, force_ai: bool = False) -> ParseResult:
    """Async smart parser with AI fallback."""
    local = local_parse(text)

    all_unknown = all(item["category"] == "andet" for item in local)
    confidence: Confidence = "none" if not local else "low" if all_unknown else "high"

    use_ai = (
        force_ai
        or (not local or all_unknown or len(text.split()) < 4)
        and ANTHROPIC_AVAILABLE
    )

    if use_ai:
        if ai_items := await ai_parse(text):
            return {
                "items": ai_items,
                "method": "ai",
                "confidence": "high",
                "original_text": text,
                "used_alternative": None,
            }

    return {
        "items": local,
        "method": "local",
        "confidence": confidence,
        "original_text": text,
        "used_alternative": None,
    }


# Sync wrapper for compatibility
def parse_sync(text: str, force_ai: bool = False) -> ParseResult:
    """Legacy sync interface."""
    return smart_parse(text, force_ai)
