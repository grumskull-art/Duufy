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
