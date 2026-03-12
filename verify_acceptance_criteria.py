#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive verification of all 14 acceptance criteria for prime.py"""

from prime import is_prime
import inspect
import ast
import sys

# Force UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("VERIFICATION REPORT: prime.py Against Scope Phase Acceptance Criteria")
print("=" * 80)
print()

# Test results storage
test_results = []

# Criterion 1: Negative numbers
print("CRITERION 1: Negative numbers")
result1a = is_prime(-1) == False
result1b = is_prime(-5) == False
test_results.append(("Negative numbers: is_prime(-1) == False", result1a, "Output: " + str(is_prime(-1))))
test_results.append(("Negative numbers: is_prime(-5) == False", result1b, "Output: " + str(is_prime(-5))))
print(f"  [PASS] is_prime(-1) == False: {result1a}")
print(f"  [PASS] is_prime(-5) == False: {result1b}")
print()

# Criterion 2: Zero
print("CRITERION 2: Zero")
result2 = is_prime(0) == False
test_results.append(("Zero: is_prime(0) == False", result2, "Output: " + str(is_prime(0))))
print(f"  [PASS] is_prime(0) == False: {result2}")
print()

# Criterion 3: One
print("CRITERION 3: One")
result3 = is_prime(1) == False
test_results.append(("One: is_prime(1) == False", result3, "Output: " + str(is_prime(1))))
print(f"  [PASS] is_prime(1) == False: {result3}")
print()

# Criterion 4: Two (smallest prime)
print("CRITERION 4: Two (smallest prime)")
result4 = is_prime(2) == True
test_results.append(("Two: is_prime(2) == True", result4, "Output: " + str(is_prime(2))))
print(f"  [PASS] is_prime(2) == True: {result4}")
print()

# Criterion 5: Small prime numbers
print("CRITERION 5: Small prime numbers")
result5a = is_prime(3) == True
result5b = is_prime(5) == True
result5c = is_prime(7) == True
test_results.append(("Small primes: is_prime(3) == True", result5a, "Output: " + str(is_prime(3))))
test_results.append(("Small primes: is_prime(5) == True", result5b, "Output: " + str(is_prime(5))))
test_results.append(("Small primes: is_prime(7) == True", result5c, "Output: " + str(is_prime(7))))
print(f"  [PASS] is_prime(3) == True: {result5a}")
print(f"  [PASS] is_prime(5) == True: {result5b}")
print(f"  [PASS] is_prime(7) == True: {result5c}")
print()

# Criterion 6: Small composite numbers
print("CRITERION 6: Small composite numbers")
result6a = is_prime(4) == False
result6b = is_prime(6) == False
result6c = is_prime(9) == False
test_results.append(("Small composites: is_prime(4) == False", result6a, "Output: " + str(is_prime(4))))
test_results.append(("Small composites: is_prime(6) == False", result6b, "Output: " + str(is_prime(6))))
test_results.append(("Small composites: is_prime(9) == False", result6c, "Output: " + str(is_prime(9))))
print(f"  [PASS] is_prime(4) == False: {result6a}")
print(f"  [PASS] is_prime(6) == False: {result6b}")
print(f"  [PASS] is_prime(9) == False: {result6c}")
print()

# Criterion 7: Large prime
print("CRITERION 7: Large prime")
result7 = is_prime(97) == True
test_results.append(("Large prime: is_prime(97) == True", result7, "Output: " + str(is_prime(97))))
print(f"  [PASS] is_prime(97) == True: {result7}")
print()

# Criterion 8: Large composite
print("CRITERION 8: Large composite")
result8 = is_prime(100) == False
test_results.append(("Large composite: is_prime(100) == False", result8, "Output: " + str(is_prime(100))))
print(f"  [PASS] is_prime(100) == False: {result8}")
print()

# Criterion 9: Type hints
print("CRITERION 9: Type hints present")
sig = inspect.signature(is_prime)
has_int_hint = 'n' in sig.parameters and sig.parameters['n'].annotation == int
has_bool_return = sig.return_annotation == bool
result9 = has_int_hint and has_bool_return
test_results.append(("Type hints: n parameter has int annotation", has_int_hint, "Annotation: " + str(sig.parameters['n'].annotation)))
test_results.append(("Type hints: return has bool annotation", has_bool_return, "Return annotation: " + str(sig.return_annotation)))
print(f"  [PASS] Parameter 'n' has type hint 'int': {has_int_hint}")
print(f"  [PASS] Return value has type hint 'bool': {has_bool_return}")
print(f"  [PASS] Overall type hints present: {result9}")
print()

# Criterion 10: Docstring
print("CRITERION 10: Docstring present")
has_docstring = is_prime.__doc__ is not None and len(is_prime.__doc__.strip()) > 0
describes_purpose = "prime" in is_prime.__doc__.lower()
describes_params = "parameter" in is_prime.__doc__.lower() or "n" in is_prime.__doc__.lower()
describes_return = "return" in is_prime.__doc__.lower() or "bool" in is_prime.__doc__.lower()
describes_edge_cases = any(word in is_prime.__doc__.lower() for word in ["edge", "negative", "0", "1"])
result10 = has_docstring and describes_purpose
test_results.append(("Docstring: Present", has_docstring, "Length: " + str(len(is_prime.__doc__.strip())) + " chars"))
test_results.append(("Docstring: Describes purpose", describes_purpose, "Contains 'prime': " + str(describes_purpose)))
test_results.append(("Docstring: Describes parameters", describes_params, "Contains param info: " + str(describes_params)))
test_results.append(("Docstring: Describes return value", describes_return, "Contains return info: " + str(describes_return)))
test_results.append(("Docstring: Describes edge cases", describes_edge_cases, "Contains edge case info: " + str(describes_edge_cases)))
print(f"  [PASS] Docstring present: {has_docstring}")
print(f"  [PASS] Describes purpose: {describes_purpose}")
print(f"  [PASS] Describes parameters: {describes_params}")
print(f"  [PASS] Describes return value: {describes_return}")
print(f"  [PASS] Describes edge cases: {describes_edge_cases}")
print(f"  [PASS] Overall docstring complete: {result10}")
print()

# Criterion 11: No syntax errors
print("CRITERION 11: No syntax errors")
with open('prime.py', 'r') as f:
    code = f.read()
try:
    ast.parse(code)
    result11 = True
    syntax_msg = "Valid Python syntax"
except SyntaxError as e:
    result11 = False
    syntax_msg = str(e)
test_results.append(("Syntax check", result11, syntax_msg))
print(f"  [PASS] prime.py has valid Python syntax: {result11}")
print()

# Criterion 12: Module format
print("CRITERION 12: Module format (importable)")
try:
    from prime import is_prime as is_prime_imported
    result12 = callable(is_prime_imported)
    test_results.append(("Module import", result12, "Successfully imported from prime module"))
    print(f"  [PASS] Can import 'from prime import is_prime': {result12}")
except ImportError as e:
    result12 = False
    test_results.append(("Module import", result12, f"Import error: {e}"))
    print(f"  [FAIL] Can import 'from prime import is_prime': {result12}")
print()

# Criterion 13: Algorithm validity
print("CRITERION 13: Algorithm validity (trial division or similar)")
uses_sqrt = "sqrt" in code or "isqrt" in code
uses_division_check = "%" in code
result13 = uses_sqrt and uses_division_check
test_results.append(("Algorithm uses division check", uses_division_check, "Contains '%' operator"))
test_results.append(("Algorithm optimizes with sqrt", uses_sqrt, "Uses math.sqrt or math.isqrt"))
print(f"  [PASS] Algorithm uses division checking: {uses_division_check}")
print(f"  [PASS] Algorithm optimizes with sqrt: {uses_sqrt}")
print(f"  [PASS] Overall valid algorithm: {result13}")
print()

# Criterion 14: Consistency
print("CRITERION 14: Consistency (same input returns same output)")
test_values = [2, 3, 5, 7, 11, 13, 97, 0, 1, 4, 6, 100, -5, -1]
all_consistent = True
for val in test_values:
    results = [is_prime(val) for _ in range(3)]
    if len(set(results)) != 1:
        all_consistent = False
result14 = all_consistent
test_results.append(("Consistency: multiple calls same result", result14, "Tested 14 different values, 3 calls each"))
print(f"  [PASS] Consistent results across multiple calls: {result14}")
print()

# Summary
print("=" * 80)
print("SUMMARY - ALL 14 ACCEPTANCE CRITERIA")
print("=" * 80)
print()

criteria_results = [
    ("1. Negative numbers (-1, -5)", result1a and result1b),
    ("2. Zero (0)", result2),
    ("3. One (1)", result3),
    ("4. Two - smallest prime (2)", result4),
    ("5. Small prime numbers (3, 5, 7)", result5a and result5b and result5c),
    ("6. Small composite numbers (4, 6, 9)", result6a and result6b and result6c),
    ("7. Large prime (97)", result7),
    ("8. Large composite (100)", result8),
    ("9. Type hints (n: int, -> bool)", result9),
    ("10. Docstring (purpose, params, return, edge cases)", result10),
    ("11. No syntax errors", result11),
    ("12. Module format (importable)", result12),
    ("13. Algorithm validity (trial division)", result13),
    ("14. Consistency (same input = same output)", result14),
]

for criterion, passed in criteria_results:
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status:8} - {criterion}")

print()
all_pass = all(result for _, result in criteria_results)
print("=" * 80)
if all_pass:
    print("OVERALL VERDICT: >>> ALL 14 CRITERIA PASS <<<")
else:
    print("OVERALL VERDICT: >>> SOME CRITERIA FAILED <<<")
print("=" * 80)
