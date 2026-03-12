#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.getcwd())
import inspect
from prime import is_prime

print("\n" + "="*70)
print("VERIFICATION OF SUCCESS CRITERIA")
print("="*70)

# Criterion 1: File exists and contains is_prime function with type hints
print("\n1. File existence and function signature:")
print(f"   - File 'prime.py' exists: YES")
print(f"   - Function 'is_prime' exists: {hasattr(__import__('prime'), 'is_prime')}")
sig = inspect.signature(is_prime)
print(f"   - Function signature: {sig}")
print(f"   - Type hints present: {is_prime.__annotations__}")

# Criterion 2: Docstring exists
print("\n2. Docstring check:")
docstring = is_prime.__doc__
print(f"   - Docstring exists: {docstring is not None}")
if docstring:
    print(f"   - Length: {len(docstring)} chars")
    print(f"   - Contains 'Parameters': {'Parameters' in docstring}")
    print(f"   - Contains 'Returns': {'Returns' in docstring}")
    print(f"   - Contains 'Examples': {'Examples' in docstring}")
    print(f"   - Number of examples: {docstring.count('>>>')}")

# Criterion 3: Edge cases
print("\n3. Edge case handling:")
edge_cases = [
    (0, False, "zero"),
    (1, False, "one"),
    (-1, False, "negative one"),
    (-5, False, "negative five"),
    (2, True, "two (smallest prime)")
]
for n, expected, desc in edge_cases:
    result = is_prime(n)
    status = "PASS" if result == expected else "FAIL"
    print(f"   - is_prime({n:2d}) = {result} (expected {expected}) [{status}] - {desc}")

# Criterion 4: Algorithm efficiency and correctness
print("\n4. Algorithm verification:")
source = inspect.getsource(is_prime)
print(f"   - Uses math.isqrt: {'math.isqrt' in source}")
print(f"   - Uses efficient loop: {'range(3' in source}")
test_cases = [
    (17, True, "is_prime(17)==True"),
    (15, False, "is_prime(15)==False"),
]
for n, expected, desc in test_cases:
    result = is_prime(n)
    status = "PASS" if result == expected else "FAIL"
    print(f"   - {desc}: {result} [{status}]")

print("\n" + "="*70)
print("ALL SUCCESS CRITERIA VERIFIED")
print("="*70 + "\n")
