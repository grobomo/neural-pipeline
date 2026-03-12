"""Cross-platform credential retrieval for Neural Pipeline.

Retrieves API keys from the OS credential store via the credential-manager
skill's claude_cred module. Falls back to keyring directly if claude_cred
is not available. Never stores secrets in plaintext.
"""
import sys
import os
from pathlib import Path


def _ensure_cred_path():
    """Add credential-manager skill to sys.path if needed."""
    cred_dir = Path.home() / ".claude" / "skills" / "credential-manager"
    cred_str = str(cred_dir)
    if cred_str not in sys.path:
        sys.path.insert(0, cred_str)


def get_api_key(credential_key: str = "NEURAL_PIPELINE/API_KEY") -> str:
    """Retrieve the Anthropic API key from the OS credential store.

    Args:
        credential_key: The service/key name in the credential store.

    Returns:
        The API key string, stripped of whitespace.

    Raises:
        RuntimeError: If the key cannot be retrieved.
    """
    # Try claude_cred first (the credential-manager skill's resolver)
    try:
        _ensure_cred_path()
        from claude_cred import resolve
        key = resolve(credential_key)
        return key.strip().replace("\n", "").replace("\r", "")
    except ImportError:
        pass
    except Exception as e:
        raise RuntimeError(f"credential-manager resolve failed: {e}") from e

    # Fallback: use keyring directly
    try:
        import keyring
        service, name = credential_key.split("/", 1)
        key = keyring.get_password(f"claude-code:{service}", name)
        if key:
            return key.strip().replace("\n", "").replace("\r", "")
        # Try alternate format
        key = keyring.get_password("claude-code", credential_key)
        if key:
            return key.strip().replace("\n", "").replace("\r", "")
    except Exception:
        pass

    raise RuntimeError(
        f"Could not retrieve {credential_key} from credential store. "
        f"Store it with: python ~/.claude/skills/credential-manager/cred_cli.py "
        f"store {credential_key} --clipboard"
    )
