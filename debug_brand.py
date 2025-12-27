"""Debug brand name handling"""
from ai_parser_optimized import local_parse, _clean_fillers, _SPLIT_PATTERN, _KNOWN_PRODUCTS

text = "riberhus mellemlagret ost"

print("Testing:", repr(text))
words = text.split()
print(f"Words: {words}")
print(f"Last word: {words[-1].lower()}")
print(f"Is 'ost' in known products? {words[-1].lower() in _KNOWN_PRODUCTS}")

# Full test
full_text = "jeg skal have øllebørd, ost, agurker, så skal jeg huske marmelade, riberhus mellemlagret ost"
result = local_parse(full_text)
print(f"\nFull parse result ({len(result)} items):")
for item in result:
    print(f"  - {item['item']} ({item['quantity']})")
