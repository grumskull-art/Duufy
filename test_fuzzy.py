#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test fuzzy matching og utydelig tale"""

from ai_parser import local_parse, smart_parse

test_cases = [
    # Forkortelser
    ("hambo og remu", ["Hamburgerryg", "Remoulade"]),
    ("tre kilo karto", ["Kartofler"]),
    # Stavefejl
    ("sømælk", ["Sødmælk"]),
    ("smæølk", ["Sødmælk"]),
    ("piskflø", ["Piskefløde"]),
    ("rugbrø", ["Rugbrød"]),
    # Gentagelser
    ("smø smø smør", ["Smør"]),
    ("mælk mælk mælk", ["Mælk"]),
    # Komplekse
    ("halv liter piskflø", ["Piskefløde"]),
    ("øh jeg sku ha den der sømælk", ["Sødmælk"]),
]

print("🧪 Testing Fuzzy Matching & Utydelig Tale")
print("=" * 70)

passed = 0
failed = 0

for text, expected in test_cases:
    result = local_parse(text)  # Test lokal først
    items = [item["item"] for item in result]

    success = all(exp in items for exp in expected)
    status = "✓" if success else "✗"

    print(f'\n{status} "{text}"')
    print(f"   Forventet: {expected}")
    print(f"   Fik:       {items}")

    if success:
        passed += 1
    else:
        failed += 1

print(f"\n{'=' * 70}")
print(f"Resultat: {passed}/{len(test_cases)} tests passed")
if failed > 0:
    print(f"⚠️ {failed} tests failed - AI vil måske håndtere dem bedre")
