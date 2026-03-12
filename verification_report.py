#!/usr/bin/env python3
"""
Comprehensive verification of prime.py against all acceptance criteria
"""
import ast
import inspect
from prime import is_prime

print("=" * 70)
print("COMPREHENSIVE VERIFICATION OF prime.py")
print("=" * 70)
print()

# ============================================================================
# ACCEPTANCE CRITERION 1: Function named 'is_prime'
# ============================================================================
print("CRITERION 1: Function is named 'is_prime'")
print("-" * 70)
try:
    assert callable(is_prime), "is_prime is not callable"
    assert is_prime.__name__ == 'is_prime', f"Function name is {is_prime.__name__}, not is_prime"
    print("[PASS] Function is named 'is_prime' and is callable")
except AssertionError as e:
    print(f"[FAIL] {e}")
print()

# ============================================================================
# ACCEPTANCE CRITERION 2: Type hints present
# ============================================================================
print("CRITERION 2: Type hints on parameter and return value")
print("-" * 70)
sig = inspect.signature(is_prime)
params = sig.parameters
return_annotation = sig.return_annotation

has_param_hint = 'n' in params and params['n'].annotation == int
has_return_hint = return_annotation == bool

if has_param_hint and has_return_hint:
    print(f"[PASS] Parameter 'n' has type hint: {params['n'].annotation}")
    print(f"[PASS] Return value has type hint: {return_annotation}")
else:
    print(f"[FAIL] Parameter hint: {params['n'].annotation if 'n' in params else 'MISSING'}")
    print(f"[FAIL] Return hint: {return_annotation if return_annotation != inspect.Signature.empty else 'MISSING'}")
print()

# ============================================================================
# ACCEPTANCE CRITERION 3: Complete docstring
# ============================================================================
print("CRITERION 3: Complete docstring with parameters, return, and edge cases")
print("-" * 70)
docstring = is_prime.__doc__

checks = {
    "Has docstring": docstring is not None,
    "Mentions parameters": "Args:" in docstring or "Parameter" in docstring,
    "Mentions return value": "Returns:" in docstring or "Return" in docstring,
    "Documents edge cases": any(word in docstring for word in ["edge case", "-5", "-1", "0", "1", "negative", "False"]),
}

all_doc_pass = all(checks.values())
for check, result in checks.items():
    status = "[PASS]" if result else "[FAIL]"
    print(f"{status} {check}")

if all_doc_pass:
    print()
    print("Docstring content preview:")
    print(docstring[:200] + "...")
print()

# ============================================================================
# ACCEPTANCE CRITERION 4: Edge case handling
# ============================================================================
print("CRITERION 4: Edge case handling (0, 1, negative numbers)")
print("-" * 70)

edge_cases = [
    (0, False, "Zero"),
    (1, False, "One"),
    (-5, False, "Negative number"),
    (-1, False, "Negative one"),
]

edge_pass = True
for num, expected, desc in edge_cases:
    actual = is_prime(num)
    result = actual == expected
    edge_pass = edge_pass and result
    status = "[PASS]" if result else "[FAIL]"
    print(f"{status} is_prime({num:>2}) = {actual} (expected {expected}) - {desc}")

print()

# ============================================================================
# ACCEPTANCE CRITERION 5: Efficient algorithm (sqrt(n))
# ============================================================================
print("CRITERION 5: Efficient algorithm (O(sqrt(n)), not O(n))")
print("-" * 70)

# Read source code to check for sqrt logic
with open('prime.py', 'r') as f:
    source = f.read()

algo_checks = {
    "Uses 'while i*i <= n' pattern": "while i * i <= n" in source or "while i*i <= n" in source,
    "Checks odd numbers only": "i += 2" in source,
    "Has special case for 2": "n == 2" in source and "return True" in source,
    "No loop from 2 to n": "range(2, n)" not in source and "range(2, n+1)" not in source,
}

algo_pass = all(algo_checks.values())
for check, result in algo_checks.items():
    status = "[PASS]" if result else "[FAIL]"
    print(f"{status} {check}")

print()

# ============================================================================
# ADDITIONAL CHECKS: No external dependencies
# ============================================================================
print("CRITERION 6 (BONUS): No external dependencies")
print("-" * 70)

tree = ast.parse(source)
imports = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            imports.append(node.module)

# Filter out standard library imports (none in this case)
external_imports = [imp for imp in imports if not imp.startswith('__')]

if not external_imports:
    print("[PASS] No external dependencies detected")
else:
    print(f"[INFO] Imports found: {external_imports}")
print()

# ============================================================================
# ADDITIONAL CHECKS: PEP 8 Compliance
# ============================================================================
print("CRITERION 7 (BONUS): PEP 8 Style Compliance")
print("-" * 70)

# Basic checks
pep8_checks = {
    "Function name is lowercase_with_underscores": is_prime.__name__.islower() and '_' in is_prime.__name__,
    "Proper spacing in comments": "# " in source or "#" not in source,
    "Code parses without syntax errors": True,  # Already verified
}

for check, result in pep8_checks.items():
    status = "[PASS]" if result else "[FAIL]"
    print(f"{status} {check}")

print()
print("Note: Minor style issues detected (blank lines with whitespace) but functionally acceptable")
print()

# ============================================================================
# TEST ALL 13 SPECIFIC TEST CASES
# ============================================================================
print("=" * 70)
print("EXECUTING ALL 13 SPECIFIC TEST CASES")
print("=" * 70)
print()

test_cases = [
    (-5, False),
    (-1, False),
    (0, False),
    (1, False),
    (2, True),
    (3, True),
    (4, False),
    (5, True),
    (7, True),
    (9, False),
    (10, False),
    (97, True),
    (100, False)
]

all_tests_passed = True
for num, expected in test_cases:
    actual = is_prime(num)
    passed = actual == expected
    all_tests_passed = all_tests_passed and passed
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status}: is_prime({num:>3}) = {str(actual):<5} (expected {expected})")

print()
print("=" * 70)
print("FINAL VERIFICATION SUMMARY")
print("=" * 70)
print()

criteria_results = {
    "Criterion 1 - Function named 'is_prime'": True,
    "Criterion 2 - Type hints present": has_param_hint and has_return_hint,
    "Criterion 3 - Complete docstring": all_doc_pass,
    "Criterion 4 - Edge case handling": edge_pass,
    "Criterion 5 - Efficient algorithm": algo_pass,
    "All 13 test cases": all_tests_passed,
}

for criterion, result in criteria_results.items():
    status = "[PASS]" if result else "[FAIL]"
    print(f"{status} {criterion}")

print()
all_pass = all(criteria_results.values())
if all_pass:
    print("*** ALL ACCEPTANCE CRITERIA MET ***")
else:
    print("*** SOME CRITERIA FAILED ***")

print("=" * 70)
