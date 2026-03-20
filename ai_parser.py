"""
AI-powered parser til indkøbslister
Bruger lokal regex først, falder tilbage til Claude API ved usikkerhed
"""

import json
import os
import re
import string
import unicodedata
from difflib import get_close_matches
from functools import lru_cache
from typing import Dict, List, Optional

import httpx
from fastapi import HTTPException

from ai_provider import get_client

# Load .env fil
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv ikke installeret, brug miljøvariabler direkte

# Prøv at importere Anthropic (valgfri)
try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic ikke installeret - kun lokal parsing tilgængelig")

# Kategorier til varer
CATEGORIES = {
    # Mejeri
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
    # Kød
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
    # Fisk
    "laks": "fisk",
    "tun": "fisk",
    "torsk": "fisk",
    "rejer": "fisk",
    # Brød
    "brød": "bager",
    "rugbrød": "bager",
    "franskbrød": "bager",
    "boller": "bager",
    # Grøntsager
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
    # Frugt
    "æbler": "frugt",
    "æble": "frugt",
    "bananer": "frugt",
    "banan": "frugt",
    "appelsiner": "frugt",
    "appelsin": "frugt",
    "pærer": "frugt",
    "citroner": "frugt",
    # Drikkevarer
    "juice": "drikkevarer",
    "cola": "drikkevarer",
    "sodavand": "drikkevarer",
    "øl": "drikkevarer",
    "vin": "drikkevarer",
    "vand": "drikkevarer",
    "kaffe": "drikkevarer",
    "te": "drikkevarer",
    # Kolonial
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
    # Husholdning
    "toiletpapir": "husholdning",
    "køkkenrulle": "husholdning",
    "sæbe": "husholdning",
    # Æg
    "æg": "æg",
}

# Standard mængder per kategori/vare
DEFAULT_QUANTITIES = {
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
    # Specifikke varer
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

# Kendt produktliste til fuzzy matching
KNOWN_PRODUCTS = list(CATEGORIES.keys())

# Forkortelser og almindelige stavefejl
PRODUCT_ALIASES = {
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
}


def fuzzy_correct(word: str) -> str:
    """Prøv at rette stavefejl og forkortelser med fuzzy matching"""
    word_lower = word.lower()

    # Check direkte aliases først
    if word_lower in PRODUCT_ALIASES:
        return PRODUCT_ALIASES[word_lower]

    # Brug fuzzy matching på kendte produkter
    matches = get_close_matches(word_lower, KNOWN_PRODUCTS, n=1, cutoff=0.7)
    if matches:
        return matches[0]

    return word


# Mængde-mønster - mere præcist
AMOUNT_PATTERN = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(l|liter|ml|dl|cl|stk|stykker?|pakke|pakker|pk|poser?|g|gram|kg|kilo|fl|flaske|flasker|ds|d\u00e5se|d\u00e5ser|bundt|net)?\s+",
    re.IGNORECASE,
)

STOPWORDS = {
    "og",
    "en",
    "et",
    "nej",
    "bare",
    "tak",
    "\u00f8h",
    "\u00f8hm",
    "ehm",
}

NUMBER_WORDS = {
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
}

UNIT_ALIASES = {
    "liter": {"liter", "l"},
    "g": {"g", "gram"},
    "kg": {"kg", "kilo"},
    "pakke": {"pakke", "pakker", "pk"},
    "pose": {"pose", "poser"},
    "d\u00e5se": {"d\u00e5se", "d\u00e5ser", "ds"},
}

ALLOWED_MULTIWORD_ITEMS = {
    "ice cream",
    "sour cream",
    "cottage cheese",
    "peanut butter",
    "bagepulver",
    "bage soda",
    "flormelis",
    "rødvin",
    "hvidvin",
}

MAX_ITEM_TOKENS = 6
STOP_PREFIXES_DA = [
    "jeg skal",
    "vi skal",
    "jeg vil",
    "vi vil",
    "skal have",
    "vil have",
    "køb",
    "hent",
    "find",
    "tilføj",
    "skriv",
    "jeg vil gerne",
    "vi vil gerne",
    "jeg skal have",
    "vi skal have",
    "mangler",
    "vi mangler",
]
STOP_PREFIXES_EN = ["i need", "we need", "buy", "get", "add", "find", "please"]
STOP_TOKENS = {
    "jeg",
    "vi",
    "skal",
    "vil",
    "køb",
    "hent",
    "find",
    "tilføj",
    "skriv",
    "hos",
    "fra",
    "please",
}


def _normalize_item_text(value: str) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", value).lower().strip()
    text = text.strip(string.punctuation)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= 1:
        return ""
    text = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text)
    return text


def strict_sanitize_items(items: List[str]) -> List[str]:
    sanitized: List[str] = []
    prefixes = STOP_PREFIXES_DA + STOP_PREFIXES_EN

    for item in items:
        cleaned = _normalize_item_text(item)
        if not cleaned:
            continue

        for _ in range(3):
            trimmed = False
            for prefix in prefixes:
                if cleaned == prefix:
                    cleaned = ""
                    trimmed = True
                    break
                if cleaned.startswith(prefix + " "):
                    cleaned = cleaned[len(prefix) :].strip()
                    trimmed = True
                    break
            if trimmed:
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if not cleaned:
                    break
                continue
            break

        if not cleaned:
            continue

        if re.fullmatch(r"\d+", cleaned):
            continue

        if cleaned.count(",") + cleaned.count(".") >= 2:
            continue

        tokens = cleaned.split()
        if len(tokens) > MAX_ITEM_TOKENS:
            continue
        if any(token in STOP_TOKENS for token in tokens):
            continue

        sanitized.append(cleaned)

    deduped: List[str] = []
    seen: set[str] = set()
    for item in sanitized:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)

    return deduped


def canonicalize_items(raw_items: List[str]) -> List[str]:
    normalized: List[str] = []
    for raw in raw_items:
        cleaned = _normalize_item_text(raw)
        if cleaned:
            normalized.append(cleaned)

    deduped: List[str] = []
    seen: set[str] = set()
    for item in normalized:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)

    item_set = set(deduped)
    survivors: List[str] = []
    for item in deduped:
        tokens = item.split()
        if len(tokens) == 2 and item not in ALLOWED_MULTIWORD_ITEMS:
            left = tokens[0]
            right = tokens[1]
            if left in item_set and right in item_set:
                continue
        survivors.append(item)

    survivors = strict_sanitize_items(survivors)
    return survivors


def _canonicalize_item_dicts(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    names: List[str] = []
    for item in items:
        name = item.get("name") or item.get("item")
        if isinstance(name, str):
            names.append(name)
        else:
            names.append("")

    canonical_names = canonicalize_items(names)
    if not canonical_names:
        return []

    lookup: Dict[str, Dict[str, object]] = {}
    for item in items:
        name = item.get("name") or item.get("item")
        if not isinstance(name, str):
            continue
        normalized = _normalize_item_text(name)
        if normalized and normalized not in lookup:
            lookup[normalized] = item

    result: List[Dict[str, object]] = []
    for name in canonical_names:
        item = lookup.get(name)
        if not item:
            continue
        cleaned = dict(item)
        if "name" in cleaned:
            cleaned["name"] = name
        if "item" in cleaned:
            cleaned["item"] = name
        result.append(cleaned)

    return result


def _parse_number(token: str) -> Optional[str]:
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    if re.match(r"^\d+(?:[.,]\d+)?$", token):
        return token.replace(",", ".")
    return None


def _is_unit(token: str) -> bool:
    return any(token in variants for variants in UNIT_ALIASES.values())


def _normalize_unit(token: str, num: str) -> str:
    if token in UNIT_ALIASES["liter"]:
        return "liter"
    if token in UNIT_ALIASES["g"]:
        return "g"
    if token in UNIT_ALIASES["kg"]:
        return "kg"
    if token in UNIT_ALIASES["pakke"]:
        return "pakke" if num == "1" else "pakker"
    if token in UNIT_ALIASES["pose"]:
        return "pose" if num == "1" else "poser"
    if token in UNIT_ALIASES["d\u00e5se"]:
        return "d\u00e5se" if num == "1" else "d\u00e5ser"
    return token


def deterministic_parse(text: str) -> List[Dict[str, object]]:
    if not text or not text.strip():
        return []

    cleaned = text.lower()
    cleaned = re.sub(r"(\d)([A-Za-z]+)", r"\1 \2", cleaned)
    cleaned = re.sub(r"[\.,;!]+", ",", cleaned)
    cleaned = re.sub(r"\+", " + ", cleaned)
    cleaned = re.sub(r"[^\w\s,\-+]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    items: List[Dict[str, object]] = []
    seen: set[str] = set()

    conjunctions = {"og", "samt", "plus", "+"}
    keep_pairs = {("salt", "peber")}

    def split_on_conjunctions(tokens: List[str]) -> List[List[str]]:
        segments: List[List[str]] = []
        current: List[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in conjunctions and current:
                j = i + 1
                next_token = None
                while j < len(tokens):
                    candidate = tokens[j]
                    if candidate in conjunctions or candidate in STOPWORDS:
                        j += 1
                        continue
                    next_token = candidate
                    break
                if next_token:
                    current_name_tokens = [
                        t
                        for t in current
                        if t not in STOPWORDS
                        and t not in conjunctions
                        and not _parse_number(t)
                        and not _is_unit(t)
                    ]
                    next_is_number = _parse_number(next_token) is not None
                    next_is_unit = _is_unit(next_token)
                    next_is_word = not next_is_number and not next_is_unit
                    keep_pair = (
                        len(current_name_tokens) == 1
                        and next_is_word
                        and (current_name_tokens[0], next_token) in keep_pairs
                    )
                    if current_name_tokens and (
                        next_is_number or (next_is_word and not keep_pair)
                    ):
                        segments.append(current)
                        current = []
                        i += 1
                        continue
            current.append(token)
            i += 1
        if current:
            segments.append(current)
        return segments

    for part in parts:
        part_tokens = [t for t in part.split() if t]
        if not part_tokens:
            continue
        for tokens in split_on_conjunctions(part_tokens):
            if not tokens:
                continue

            num = _parse_number(tokens[0])
            idx = 1 if num else 0
            unit = None
            if num and idx < len(tokens) and _is_unit(tokens[idx]):
                unit = _normalize_unit(tokens[idx], num)
                idx += 1

            name_tokens = tokens[idx:]
            filtered = []
            for token in name_tokens:
                if token in STOPWORDS:
                    continue
                if _parse_number(token):
                    continue
                if _is_unit(token):
                    continue
                filtered.append(token)

            if not filtered:
                continue

            if (
                not num
                and not unit
                and "salt" in tokens
                and "og" in tokens
                and "peber" in tokens
            ):
                name = "salt og peber"
            else:
                name = " ".join(filtered).strip()
                if not name or name in STOPWORDS:
                    continue
                if name in NUMBER_WORDS:
                    continue

            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            quantity = num or "1"
            if num and unit:
                quantity = f"{num} {unit}"

            items.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "warnings": [],
                }
            )

    return items


def normalize_unit(unit: str, num: Optional[str] = None) -> str:
    unit_lower = unit.lower()
    if unit_lower in ["l", "liter"]:
        return "liter"
    if unit_lower in ["kg", "kilo"]:
        return "kg"
    if unit_lower in ["g", "gram"]:
        return "g"
    if unit_lower in ["ml", "milliliter"]:
        return "ml"
    if unit_lower in ["dl", "deciliter"]:
        return "dl"
    if unit_lower in ["cl", "centiliter"]:
        return "cl"
    if unit_lower in ["stk", "stykker", "stykke"]:
        return "stk"
    if unit_lower in ["pk", "pakke", "pakker"]:
        return "pakke" if num == "1" else "pakker"
    if unit_lower in ["pose", "poser"]:
        return "pose" if num == "1" else "poser"
    if unit_lower in ["fl", "flaske", "flasker"]:
        return "flaske" if num == "1" else "flasker"
    if unit_lower in ["ds", "d\u00e5se", "d\u00e5ser"]:
        return "d\u00e5se" if num == "1" else "d\u00e5ser"
    if unit_lower in ["bundt", "net"]:
        return unit_lower
    return unit


def get_category(item_name: str) -> str:
    """Find kategori for en vare"""
    item_lower = item_name.lower()
    for key, category in CATEGORIES.items():
        if key in item_lower:
            return category
    return "andet"


def get_default_quantity(item_name: str) -> str:
    """Gaet standard maengde for en vare"""
    return "1"


def smart_split_by_products(text: str) -> List[str]:
    """Splitter tekst ved kendte produkter for at adskille varer uden separator"""
    words = text.strip().split()
    if len(words) <= 2:
        return [text]

    parts = []
    current_part = []
    last_product_idx = -1

    for i, word in enumerate(words):
        # Check om ordet er et kendt produkt
        is_product = any(
            word == p or word.startswith(p) or p.startswith(word)
            for p in CATEGORIES.keys()
        )

        # Check om næste ord starter en ny mængde
        next_word = words[i + 1] if i < len(words) - 1 else ""
        next_is_quantity = bool(
            re.match(
                r"^(\d+|en|et|to|tre|fire|fem|halvanden)$", next_word, re.IGNORECASE
            )
        )
        next_is_product = any(
            next_word == p or next_word.startswith(p) or p.startswith(next_word)
            for p in CATEGORIES.keys()
        )

        current_part.append(word)

        if is_product:
            last_product_idx = len(current_part) - 1

            # Hvis næste ord er mængde eller nyt produkt, afslut denne del
            if next_is_quantity or (next_is_product and i < len(words) - 1):
                parts.append(" ".join(current_part))
                current_part = []
                last_product_idx = -1

    # Tilføj resterende ord
    if current_part:
        parts.append(" ".join(current_part))

    return parts if parts else [text]


def local_parse(text: str) -> List[Dict]:
    """Parser tekst med regex - hurtig lokal parsing"""
    text = text.lower().strip()

    # Fjern fyldord fra starten - MEGET mere omfattende
    fillers = [
        r"^(øh|ehm|øhm|nå|nåh|altså|ikke|jo|bare)\s+",
        r"^(jeg skal have|vi skal have|skal have|jeg skal|vi skal)\s+",
        r"^(jeg|vi|man|den|det|de|der|den der|det der|de der)\s+",
        r"^(det der|ham der|hende der|den slags|du ved|jeg tænker)\s+",
        r"^(sku ha|sku have|ska ha|ska have)\s+",  # Slang/dialekt versioner
        r"^(skal have|skal bruge|skal købe|mangler|vi mangler)\s+",
        r"^(noget|lidt|lidt af|lidt af det|nogen|nogle)\s+",
        r"^(tilføj|køb|hent|tag|skriv|sæt)\s+",
        r"^(en|et|den|det)\s+(?!liter|kilo|kg|l\s)",  # Men ikke før enheder
    ]

    # Kør fyldords-fjernelse flere gange for at fange alle
    for _ in range(3):  # Max 3 iterationer
        old_text = text
        for filler in fillers:
            text = re.sub(filler, "", text, flags=re.IGNORECASE)
        if text == old_text:  # Ingen ændringer mere
            break

    # Split på eksplicitte separatorer
    parts = re.split(r"\s+og\s+|\s*,\s*|\s+samt\s+|\s+plus\s+", text)

    # For hver del, prøv at splitte på kendte produkter
    all_parts = []
    for part in parts:
        all_parts.extend(smart_split_by_products(part))

    parsed_items = []

    # Ordtal til tal mapping
    word_to_num = {
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

    for part in all_parts:
        part = part.strip()
        if not part or len(part) < 2:
            continue

        item_name = part
        quantity = ""

        # Prøv specielle mønstre først

        # "tre/fire/fem kilo/liter X" (ordtal + enhed)
        ordtal_match = re.match(
            r"^(en|et|to|tre|fire|fem|seks|syv|otte|ni|ti|halvanden|halvandet)\s+(liter|l|ml|dl|cl|stk|stykker|stykke|pakke|pakker|pk|poser|pose|g|gram|kg|kilo|fl|flaske|flasker|ds|d\u00e5se|d\u00e5ser|bundt|net)\s+(.+)$",
            part,
            re.IGNORECASE,
        )
        if ordtal_match:
            num_word = ordtal_match.group(1).lower()
            unit = ordtal_match.group(2)
            item_name = ordtal_match.group(3).strip()

            # Konverter ordtal til tal
            num = word_to_num.get(num_word, num_word)

            # Normaliser enhed
            unit = normalize_unit(unit, num)
            quantity = f"{num} {unit}"

        # "halvanden liter/kilo X"
        elif re.match(
            r"^(halvanden|halvandet)\s+(liter|l|kilo|kg)\s+", part, re.IGNORECASE
        ):
            halvanden_match = re.match(
                r"^(halvanden|halvandet)\s+(liter|l|kilo|kg)\s+(.+)$",
                part,
                re.IGNORECASE,
            )
            if halvanden_match:
                unit = halvanden_match.group(2)
                item_name = halvanden_match.group(3).strip()
                unit_norm = normalize_unit(unit, "1.5")
                quantity = f"1.5 {unit_norm}"

        # "en/et/halv/halvt liter/kilo X"
        elif re.match(
            r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+", part, re.IGNORECASE
        ):
            unit_match = re.match(
                r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+(.+)$", part, re.IGNORECASE
            )
            if unit_match:
                quantity_word = unit_match.group(1).lower()
                unit_word = unit_match.group(2).lower()
                item_name = unit_match.group(3).strip()

                # Bestem mængde
                if quantity_word in ["halv", "halvt"]:
                    num = "0.5"
                else:
                    num = "1"

                if unit_word in ["liter", "l"]:
                    quantity = f"{num} {normalize_unit(unit_word, num)}"
                elif unit_word in ["kilo", "kg"]:
                    quantity = f"{num} {normalize_unit(unit_word, num)}"

        # "X l/liter/kg/stk Y"
        elif re.match(r"^\d", part):
            amount_match = AMOUNT_PATTERN.match(part)
            if amount_match:
                num = amount_match.group(1)
                unit = amount_match.group(2) or "stk"
                unit = normalize_unit(unit, num)
                quantity = f"{num} {unit}"
                # Resten er item_name
                item_name = part[amount_match.end() :].strip()

        # Ryd GRUNDIGT op i item_name - fjern alle fyldord
        item_name = re.sub(
            r"^(en|et|den|det|noget|nogen|nogle|lidt|den der|det der)\s+",
            "",
            item_name,
            flags=re.IGNORECASE,
        )
        item_name = re.sub(r"^(den|det|der)\s+", "", item_name, flags=re.IGNORECASE)
        item_name = item_name.strip()

        if not item_name:
            continue

        # Prøv fuzzy correction på produktnavnet
        item_name = fuzzy_correct(item_name)

        # Sæt default mængde hvis ikke fundet
        if not quantity:
            quantity = get_default_quantity(item_name)

        # Find kategori
        category = get_category(item_name)

        parsed_items.append(
            {"item": item_name.capitalize(), "quantity": quantity, "category": category}
        )

    # Fjern duplikater - behold første forekomst
    seen = set()
    unique_items = []
    for item in parsed_items:
        item_key = item["item"].lower()
        if item_key not in seen:
            seen.add(item_key)
            unique_items.append(item)

    return unique_items


def opus_parse(text: str) -> List[Dict]:
    """Parser tekst med Claude API - for komplekse sætninger"""
    if not ANTHROPIC_AVAILABLE:
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY ikke sat")
        return []

    try:
        client = get_client()

        prompt = f"""Du er en intelligent dansk indkøbsassistent. Brugeren taler ofte UTYDELIGT med dårligt/mumlet dansk.
Dit job: Forstå hvad de MENER og udtræk kun de relevante produkter.

🎯 HOVEDOPGAVE:
- Parser utydelig tale, stavefejl, afbrudte ord
- Gæt det mest sandsynlige produkt ved tvivl
- Ignorer ALT der ikke er produkter

❌ FJERN ALTID:
- Fyldord: "jeg skal have", "vi mangler", "skal købe"
- Pejleord: "den der", "det der", "ham der", "du ved"
- Samtale: "øh", "ehm", "altså", "ikke", "jo"
- Gentagelser: "mælk mælk mælk" → kun én "Mælk"
- Mumlen og pauser

✅ RET AUTOMATISK:
- "sømælk", "smæølk" → "Sødmælk"
- "rugbrø" → "Rugbrød"
- "hambo" → "Hamburgerryg"
- "remu" → "Remoulade"
- "piskflø" → "Piskefløde"
- "karto" → "Kartofler"

📝 EKSEMPLER:
"jæ ska den der smæølk" → Sødmælk (1 L)
"altså eh rugbrø rugbrød og mælk" → Rugbrød (1 stk), Mælk (1 L)
"øh jeg tænker lidt af det der hambo" → Hamburgerryg (1 pk)
"halv liter piskflø" → Piskefløde (0.5 L)
"tre kilo karto" → Kartofler (3 kg)
"smø smø smør" → Smør (250 g)  [kun én gang!]
"hambo og den der med remu" → Hamburgerryg (1 pk), Remoulade (1 stk)

📦 KATEGORIER:
mejeri, kød, fisk, bager, grønt, frugt, drikkevarer, kolonial, husholdning, æg, andet

🔧 OUTPUT (KUN JSON):
[
  {"item": "Produktnavn", "quantity": "1 enhed", "category": "kategori"}
]

🎤 BRUGERENS UTYDELIGE TALE:
"{text}"

RETURNÉR KUN JSON!"""

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Bedre kvalitet, stadig billig
            max_tokens=800,
            temperature=0.3,  # Lav temperatur for konsistens
            messages=[{"role": "user", "content": prompt}],
            timeout=60.0,
        )

        result_text = response.content[0].text.strip()

        # Fjern eventuelle markdown code blocks
        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)

        parsed = json.loads(result_text)

        # Valider at det er en liste
        if not isinstance(parsed, list):
            print(f"⚠️ AI returnerede ikke en liste: {type(parsed)}")
            return []

        # Valider hvert item
        valid_items = []
        for item in parsed:
            if (
                isinstance(item, dict)
                and "item" in item
                and "quantity" in item
                and "category" in item
            ):
                valid_items.append(item)
            else:
                print(f"⚠️ Ugyldigt item fra AI: {item}")

        return valid_items
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timed out")
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse fejl: {e}")
        print(f"   Raw response: {result_text[:200]}...")
        return []
    except Exception as e:
        print(f"⚠️ Claude API fejl: {e}")
        return []


@lru_cache(maxsize=256)
def smart_parse(text: str, force_ai: bool = False) -> Dict:
    """
    Smart parser - deterministisk lokalt, AI fallback ved behov.
    """
    local_items = deterministic_parse(text)
    local_result = []
    for item in local_items:
        name = item.get("name", "")
        if not name:
            continue
        quantity = item.get("quantity", "1")
        warnings = item.get("warnings", [])
        local_result.append(
            {
                "item": name,
                "name": name,
                "quantity": quantity,
                "category": get_category(name),
                "warnings": warnings,
            }
        )

    local_result = _canonicalize_item_dicts(local_result)

    has_items = len(local_result) > 0
    all_unknown = (
        all(item["category"] == "andet" for item in local_result) if has_items else True
    )
    short_input = len(text.split()) <= 2
    very_short = len(text.split()) < 4

    confidence = "high"
    if all_unknown and has_items:
        confidence = "low"
    elif not has_items:
        confidence = "none"

    use_ai = force_ai or (confidence in ["low", "none"] and ANTHROPIC_AVAILABLE)
    if not has_items or all_unknown or very_short:
        use_ai = force_ai or ANTHROPIC_AVAILABLE

    if use_ai and not short_input:
        ai_result = opus_parse(text)
        if ai_result:
            ai_result = _canonicalize_item_dicts(ai_result)
            unique_items = []
            seen = set()
            for item in ai_result:
                name = item["item"].strip().lower()
                if name not in seen:
                    unique_items.append(item)
                    seen.add(name)
            ai_result = unique_items
            return {
                "items": ai_result,
                "method": "ai",
                "confidence": "high",
                "original_text": text,
                "used_alternative": None,
            }

    unique_items = []
    seen = set()
    for item in local_result:
        name = item["item"].strip().lower()
        if name not in seen:
            unique_items.append(item)
            seen.add(name)
    local_result = unique_items

    return {
        "items": local_result,
        "method": "local",
        "confidence": confidence,
        "original_text": text,
        "used_alternative": None,
    }


# Test
if __name__ == "__main__":
    test_phrases = [
        # Grundlæggende
        "2 liter mælk",
        "vi mangler mælk og brød",
        "et kilo kartofler hamburgerryg og remoulade",
        # Med fyldord
        "jeg skal have den der sødmælk",
        "vi mangler noget rugbrød",
        "skal have øh tre kilo kartofler",
        # Komplekse
        "halvanden liter mælk og 3 bananer",
        "skal have noget kaffe og toiletpapir",
        "den der remoulade og det der øh bacon",
        # Edge cases
        "det der",  # Meget vagt
        "jeg skal have noget",  # Intet produkt
        "sødmælk",  # Simpelt
    ]

    print("🧪 Testing AI Parser\n" + "=" * 50)
    for phrase in test_phrases:
        result = smart_parse(phrase, force_ai=False)
        print(f"\n📝 '{phrase}'")
        print(f"   Metode: {result['method']} | Tillid: {result['confidence']}")
        if result["items"]:
            for item in result["items"]:
                print(f"   ✓ {item['item']}: {item['quantity']} ({item['category']})")
        else:
            print("   ✗ Ingen varer fundet")
