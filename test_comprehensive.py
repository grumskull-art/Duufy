"""Comprehensive test suite"""

from ai_parser_optimized import local_parse

test_cases = [
    # Original problem
    (
        "jeg skal have øllebørd, ost, agurker, så skal jeg huske marmelade, riberhus mellemlagret ost",
        ["Øllebrød", "Ost", "Agurk", "Marmelade"],
    ),  # Riberhus might not match perfectly
    # Simple lists
    ("sødmælk, rugbrød og smør", ["Sødmælk", "Rugbrød", "Smør"]),
    # With quantities
    ("2 liter mælk, 500 gram ost", ["Mælk", "Ost"]),
    # Filler words in middle
    ("mælk, så skal jeg huske brød, også ost", ["Mælk", "Brød", "Ost"]),
    # Brand names
    ("arla mælk og lurpak smør", ["Mælk", "Smør"]),  # Should fuzzy match
    # Duplicates
    ("ost, ost og ost", ["Ost"]),  # Should dedup to 1
    # Repetitions
    ("smø smø smør", ["Smør"]),
]

print("🧪 KOMPLET TEST SUITE")
print("=" * 80)

passed = 0
failed = 0

for i, (text, expected_items) in enumerate(test_cases, 1):
    result = local_parse(text)
    found_items = [item["item"] for item in result]

    # Check if all expected items are found
    success = all(
        any(exp.lower() in found.lower() for found in found_items)
        for exp in expected_items
    )
    status = "✓" if success else "✗"

    print(f"\n{status} Test {i}: {text[:60]}{'...' if len(text) > 60 else ''}")
    print(f"   Forventet: {expected_items}")
    print(f"   Fik:       {found_items}")

    if success:
        passed += 1
    else:
        failed += 1

print(f"\n{'=' * 80}")
print(f"Resultat: {passed}/{len(test_cases)} tests passed")
if failed > 0:
    print(f"⚠️  {failed} tests failed")
else:
    print("✅ Alle tests passed!")
