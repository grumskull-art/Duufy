"""Debug 'også' issue"""
from ai_parser_optimized import _clean_fillers, _SPLIT_PATTERN, local_parse

text = "mælk, så skal jeg huske brød, også ost"

print("ORIGINAL:", repr(text))
print()

cleaned = _clean_fillers(text)
print("AFTER CLEAN_FILLERS:", repr(cleaned))
print()

parts = _SPLIT_PATTERN.split(cleaned)
print("AFTER SPLIT:")
for i, p in enumerate(parts):
    print(f"  {i}: {repr(p)}")
print()

# Check if each part starts with "også"
for p in parts:
    if p.strip().lower().startswith('også'):
        print(f"⚠️  Part starts with 'også': {repr(p)}")

result = local_parse(text)
print("\nFINAL RESULT:")
for item in result:
    print(f"  - {item['item']}")
