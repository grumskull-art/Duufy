"""Test lange sætninger som brugeren rapporterer"""
from ai_parser_optimized import local_parse, smart_parse

test_input = "jeg skal have øllebørd, ost, agurker, så skal jeg huske marmelade, riberhus mellemlagret ost"

print("🧪 TESTER BRUGERENS PROBLEM\n")
print("=" * 80)
print(f"Input: {test_input}\n")

# Test lokal parsing
result = local_parse(test_input)
print(f"Antal items fundet: {len(result)}\n")

for i, item in enumerate(result, 1):
    print(f"{i}. {item['item']} ({item['quantity']}) - kategori: {item['category']}")

print("\n" + "=" * 80)

# Forventede resultater
expected = ["Øllebrød", "Ost", "Agurker", "Marmelade", "Riberhus mellemlagret ost"]
found_items = [item['item'] for item in result]

print("\n📋 ANALYSE:")
print(f"Forventet: {expected}")
print(f"Fået:      {found_items}")

# Check for duplikater
duplicates = [item for item in found_items if found_items.count(item) > 1]
if duplicates:
    print(f"\n⚠️  DUPLIKATER FUNDET: {set(duplicates)}")

# Check for missing
missing = [exp for exp in expected if exp not in found_items]
if missing:
    print(f"⚠️  MANGLER: {missing}")
