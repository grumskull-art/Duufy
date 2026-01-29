"""Test image integration with AI parser"""

from ai_parser_optimized import smart_parse

print("🧪 TESTER BILLEDE-INTEGRATION\n")
print("=" * 50)

# Test 1: Lokal parsing med billede
result = smart_parse("sødmælk og rugbrød")
print('\n1. Test: "sødmælk og rugbrød"')
print(f'   Method: {result["method"]}')
print(f'   Confidence: {result["confidence"]}')
for item in result["items"]:
    print(f'   ✓ {item["item"]}: {item["image_url"]}')

# Test 2: Fuzzy matching
result = smart_parse("sømælk hambo")
print('\n2. Test: "sømælk hambo" (fuzzy)')
for item in result["items"]:
    print(f'   ✓ {item["item"]}: {item["image_url"]}')

# Test 3: Unknown product (fallback)
result = smart_parse("noget mærkeligt produkt")
print('\n3. Test: "noget mærkeligt produkt" (unknown)')
for item in result["items"]:
    print(f'   ✓ {item["item"]}: {item["image_url"]}')

# Test 4: With quantity
result = smart_parse("2 liter mælk")
print('\n4. Test: "2 liter mælk"')
for item in result["items"]:
    print(f'   ✓ {item["item"]} ({item["quantity"]}): {item["image_url"]}')

print("\n" + "=" * 50)
print("✅ Alle tests gennemført!")
print("\nBillede-struktur:")
print("  - Produkter i image_map.json får specific URLs")
print("  - Unknown produkter får category fallback")
print("  - CDN-ready struktur (/assets/images/...)")
