#!/usr/bin/env python
"""Verify optimized version passes all tests."""
from ai_parser_optimized import local_parse

test_cases = [
    ("hambo og remu", ["Hamburgerryg", "Remoulade"]),
    ("tre kilo karto", ["Kartofler"]),
    ("sømælk", ["Sødmælk"]),
    ("smæølk", ["Sødmælk"]),
    ("piskflø", ["Piskefløde"]),
    ("rugbrø", ["Rugbrød"]),
    ("smø smø smør", ["Smør"]),
    ("mælk mælk mælk", ["Mælk"]),
    ("halv liter piskflø", ["Piskefløde"]),
    ("øh jeg sku ha den der sømælk", ["Sødmælk"]),
]

passed = sum(
    all(exp in [i['item'] for i in local_parse(text)] for exp in expected)
    for text, expected in test_cases
)

print(f"✅ {passed}/{len(test_cases)} tests passed")
assert passed == len(test_cases), "Some tests failed!"
