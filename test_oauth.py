"""Test API key retrieval and SDK call."""
import sys
import os
sys.path.insert(0, os.path.expanduser('~/.claude/skills/credential-manager'))
from claude_cred import resolve

print("[1] Retrieving NEURAL_PIPELINE/API_KEY from credential store...")
try:
    key = resolve("NEURAL_PIPELINE/API_KEY")
    key = key.strip().replace('\n', '').replace('\r', '')
    print(f"    OK - Key retrieved ({len(key)} chars, starts with {key[:12]}...)")
except Exception as e:
    print(f"    FAIL - {e}")
    sys.exit(1)

print("[2] Creating Anthropic client...")
try:
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    print("    OK - Client created")
except Exception as e:
    print(f"    FAIL - {e}")
    sys.exit(1)

print("[3] Making test API call (claude-haiku-4-5-20251001, 10 max tokens)...")
try:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": "Say hello in 3 words."}]
    )
    print(f"    OK - Response: {response.content[0].text}")
    print(f"    Model: {response.model}")
    print(f"    Usage: {response.usage.input_tokens} in, {response.usage.output_tokens} out")
except Exception as e:
    print(f"    FAIL - {type(e).__name__}: {e}")
    sys.exit(1)

print("\n[PASS] API key works with Anthropic SDK.")
