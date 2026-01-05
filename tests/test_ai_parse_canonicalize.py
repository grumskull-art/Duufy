import unicodedata

from ai_parser import canonicalize_items


def test_canonicalize_dedup_and_combos():
    raw = ["mælk mælk", "mælk", "honning mælk", "honning"]
    assert canonicalize_items(raw) == ["mælk", "honning"]


def test_canonicalize_no_substring_drop():
    raw = ["appelsin", "appelsinjuice"]
    assert canonicalize_items(raw) == ["appelsin", "appelsinjuice"]


def test_canonicalize_drop_combo_when_parts_exist():
    raw = ["honning", "mælk", "honning mælk"]
    assert canonicalize_items(raw) == ["honning", "mælk"]


def test_canonicalize_preserves_allowed_multiword():
    raw = ["ice", "cream", "ice cream"]
    result = canonicalize_items(raw)
    assert "ice cream" in result


def test_canonicalize_normalizes_unicode():
    s1 = unicodedata.normalize("NFC", "mælk")
    s2 = unicodedata.normalize("NFD", "mælk")
    assert canonicalize_items([s1, s2]) == ["mælk"]


def test_strict_trims_prefix_phrase():
    raw = ["jeg skal torskeroegn"]
    assert canonicalize_items(raw) == ["torskeroegn"]


def test_strict_drops_internal_stop_tokens():
    raw = ["mælk jeg skal torskeroegn"]
    assert canonicalize_items(raw) == []


def test_strict_drops_long_sentence():
    raw = ["hamburgerryg rullepølse pizza leverpostej hos ralleost"]
    assert canonicalize_items(raw) == []


def test_strict_token_limit_6_allows_reasonable_multiword():
    raw = ["frisk basilikum", "extra jomfru olivenolie"]
    out = canonicalize_items(raw)
    assert "frisk basilikum" in out
    assert "extra jomfru olivenolie" in out
