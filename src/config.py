"""Configuration loader for Neural Pipeline.

Reads system/config.yaml and provides typed access to all settings.
Resolves the project root dynamically using pathlib -- no hardcoded paths.
"""
import hashlib
from pathlib import Path
from typing import Any

import yaml


def get_project_root() -> Path:
    """Get the project root directory (parent of src/)."""
    return Path(__file__).resolve().parent.parent


def project_slug(project_path: str | Path) -> str:
    """Generate '{name}-{hash6}' from an absolute project path.

    Readable folder name with uniqueness guarantee so two projects
    named 'app' in different directories don't collide.
    """
    p = Path(project_path).resolve()
    h = hashlib.sha256(str(p).encode()).hexdigest()[:6]
    return f"{p.name}-{h}"


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
        self._project_slug: str | None = None

    def set_project(self, project_path: str | Path):
        """Set project context from full path. All pipeline dirs become project-scoped."""
        self._project_slug = project_slug(project_path)

    def set_project_slug(self, slug: str):
        """Set project context from slug directly (used by monitor/runners)."""
        self._project_slug = slug

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
        # Intentionally high. The first API call rejects this with the real
        # limit for the model (which varies by proxy config). _api_call_with_retry
        # catches the error, extracts the correct value, caches it in
        # AgentBase._resolved_max_tokens, and retries. This auto-discovers
        # max_tokens for any model without hardcoding.
        return 128000

    def threshold(self, name: str) -> Any:
        return self._data["thresholds"][name]

    def happiness_config(self) -> dict[str, Any]:
        return self._data["happiness"]

    def pain_severity(self, signal_type: str) -> int:
        """Get happiness impact for a pain signal type."""
        pain_map = self._data.get("pain_severity", {})
        return pain_map.get(signal_type, pain_map.get("default", 3))

    # Path helpers
    def pipeline_dir(self) -> Path:
        if self._project_slug:
            return self.root / "pipeline" / "projects" / self._project_slug
        return self.root / "pipeline"

    def phase_dir(self, phase: str) -> Path:
        return self.pipeline_dir() / phase

    def all_project_dirs(self) -> list[Path]:
        """List all project dirs under pipeline/projects/."""
        projects_root = self.root / "pipeline" / "projects"
        if not projects_root.is_dir():
            return []
        return [d for d in sorted(projects_root.iterdir()) if d.is_dir()]

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
