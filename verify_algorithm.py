import math

# Verify the algorithm uses i * i <= n (which is equivalent to i <= sqrt(n))
# For n = 100:
n = 100
sqrt_n = math.sqrt(n)
print(f"For n = {n}, sqrt(n) = {sqrt_n}")
print(f"Algorithm uses: while i * i <= n")
print(f"For the last iteration: i = {int(sqrt_n)}, i*i = {int(sqrt_n)**2}")
print(f"This means it checks divisors up to sqrt(n), not all numbers up to n.")
print(f"This is O(sqrt(n)) complexity, which is efficient.")

# Let's trace through the algorithm for n = 97 (prime)
print("\n=== TRACE FOR n = 97 ===")
n = 97
i = 3
checks = 0
while i * i <= n:
    checks += 1
    i += 2
print(f"Number of iterations: {checks}")
print(f"Checked divisors: 3, 5, 7, 9 (sqrt(97) ~= {math.sqrt(97):.2f})")

# For a naive algorithm checking all numbers up to n:
print(f"\nNaive algorithm would check {n-2} divisors (2 to {n-1})")
print(f"Optimized algorithm checks only {checks} divisors")
print(f"Efficiency gain: {(n-2)//checks}x faster")
