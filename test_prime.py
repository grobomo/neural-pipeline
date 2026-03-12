#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.getcwd())

from prime import is_prime

print("="*60)
print("TESTING is_prime() function")
print("="*60)

test_cases = [
    (-5, False, "negative number"),
    (0, False, "zero"),
    (1, False, "one"),
    (2, True, "smallest prime"),
    (3, True, "small odd prime"),
    (4, False, "even composite"),
    (15, False, "odd composite"),
    (17, True, "odd prime"),
    (100, False, "large even composite"),
    (97, True, "large prime"),
    (13, True, "medium prime"),
    (10, False, "medium composite"),
]

passed = 0
failed = 0

for n, expected, description in test_cases:
    result = is_prime(n)
    if result == expected:
        status = "PASS"
        passed += 1
    else:
        status = "FAIL"
        failed += 1
    print(f"is_prime({n:3d}) = {str(result):5s} (expected {str(expected):5s}) - {status} - {description}")

print("="*60)
print(f"Results: {passed} passed, {failed} failed")
print("="*60)

if failed == 0:
    print("SUCCESS: All tests passed!")
    sys.exit(0)
else:
    print("FAILURE: Some tests failed!")
    sys.exit(1)
