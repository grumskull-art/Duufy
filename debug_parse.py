"""Debug parsing pipeline"""
from ai_parser_optimized import local_parse, _clean_fillers, _SPLIT_PATTERN

text = "jeg skal have øllebørd, ost, agurker, så skal jeg huske marmelade, riberhus mellemlagret ost"

print("ORIGINAL TEXT:")
print(repr(text))
print()

print("EFTER FILLER REMOVAL:")
cleaned = _clean_fillers(text)
print(repr(cleaned))
print()

print("SPLIT RESULT:")
parts = _SPLIT_PATTERN.split(cleaned)
for i, p in enumerate(parts):
    print(f"{i}: {repr(p)}")
print()

print("FINAL PARSE:")
result = local_parse(text)
for item in result:
    print(f"  - {item['item']} ({item['quantity']})")
