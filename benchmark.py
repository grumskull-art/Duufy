#!/usr/bin/env python
"""Performance benchmark comparing old vs optimized parser."""
import time
from ai_parser import local_parse as old_parse, smart_parse as old_smart
from ai_parser_optimized import local_parse as new_parse, smart_parse as new_smart

TEST_CASES = [
    "jeg skal have den der sødmælk",
    "tre kilo kartofler og to liter mælk",
    "hambo og remu",
    "øh jeg sku ha den der sømælk og rugbrø",
    "halvanden liter piskflø",
    "mælk mælk mælk",
] * 100  # 600 total parses

def benchmark(name: str, func, *args):
    start = time.perf_counter()
    for text in TEST_CASES:
        func(text, *args)
    elapsed = time.perf_counter() - start
    ops_per_sec = len(TEST_CASES) / elapsed
    print(f"{name:20} {elapsed:.3f}s  ({ops_per_sec:.0f} ops/s)")
    return elapsed

print("🚀 Performance Benchmark\n" + "="*50)
old_time = benchmark("Old local_parse", old_parse)
new_time = benchmark("New local_parse", new_parse)
speedup = old_time / new_time
print(f"\n💨 Speedup: {speedup:.2f}x faster")
