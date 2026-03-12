"""Configuration loader for Neural Pipeline.

Reads system/config.yaml and provides typed access to all settings.
Resolves the project root dynamically using pathlib -- no hardcoded paths.
"""
from pathlib import Path
from typing import Any

import yaml


def get_project_root() -> Path:
    """Get the project root directory (parent of src/)."""
    return Path(__file__).resolve().parent.parent


def load_config() -> dict[str, Any]:
    """Load and return the system config."""
    config_path = get_project_root() / "system" / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


class Config:
    """Typed configuration access."""

    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data or load_config()
        self.root = get_project_root()

    @property
    def credential_key(self) -> str:
        return self._data["credential_key"]

    @property
    def auth_token_key(self) -> str:
        return self._data.get("auth_token_key", self._data["credential_key"])

    @property
    def base_url(self) -> str | None:
        return self._data.get("base_url")

    @property
    def env_vars(self) -> dict[str, str]:
        return self._data.get("env", {})

    @property
    def phases(self) -> list[str]:
        return self._data["phases"]

    @property
    def pipeline_phases(self) -> list[str]:
        """Phases that have managers/workers (excludes input and output)."""
        return [p for p in self.phases if p not in ("input", "output")]

    def model_for(self, role: str) -> str:
        return self._data["models"].get(role, "claude-sonnet-4-6")

    def max_tokens_for(self, role: str) -> int:
        return self._data["max_tokens"].get(role, 4096)

    def threshold(self, name: str) -> Any:
        return self._data["thresholds"][name]

    def happiness_config(self) -> dict[str, Any]:
        return self._data["happiness"]

    # Path helpers
    def pipeline_dir(self) -> Path:
        return self.root / "pipeline"

    def phase_dir(self, phase: str) -> Path:
        return self.pipeline_dir() / phase

    def ego_dir(self) -> Path:
        return self.root / "ego"

    def monitor_dir(self) -> Path:
        return self.root / "monitor"

    def system_dir(self) -> Path:
        return self.root / "system"

    def completed_dir(self) -> Path:
        return self.root / "completed"

    def failed_dir(self) -> Path:
        return self.root / "failed"

    def paused_dir(self) -> Path:
        return self.root / "paused"

    def blocked_dir(self) -> Path:
        return self.root / "blocked"
