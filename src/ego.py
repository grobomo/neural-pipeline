"""Ego agent for Neural Pipeline.

The sole interface to the system. Called by TUI (cct) via shell alias.
Creates tasks, reviews results, manages happiness, delegates investigations.

Usage:
  python -m src.ego "build me a web scraper"
  python -m src.ego "status"
  python -m src.ego "review task 0003"
  python -m src.ego "approve task 0003"
  python -m src.ego "reject task 0003 -- tests don't pass"
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .agent_base import AgentBase
from .config import Config


class Ego(AgentBase):
    """The prefrontal cortex of the Neural Pipeline."""

    def __init__(self, config: Config | None = None, folder_name: str = ""):
        cfg = config or Config()
        log_dir = cfg.ego_dir() / "logs"
        
        # Store folder_name for per-folder task ID counter
        self.folder_name = folder_name

        # Load reference
        reference = ""
        ref_path = cfg.ego_dir() / "reference.md"
        if ref_path.exists():
            reference = ref_path.read_text(encoding="utf-8")

        # Load ego system prompt
        ego_prompt_path = cfg.system_dir() / "agents" / "ego.md"
        if ego_prompt_path.exists():
            ego_prompt = ego_prompt_path.read_text(encoding="utf-8")
        else:
            ego_prompt = ""

        system_prompt = self._build_system_prompt(reference, ego_prompt)

        super().__init__(
            role="ego",
            log_dir=log_dir,
            config=cfg,
            system_prompt=system_prompt,
        )
        self.state = self._load_state()

    def _build_system_prompt(self, reference: str, ego_prompt: str) -> str:
        parts = [
            "You are the Ego -- the sole interface to the Neural Pipeline.",
            "You receive all external input, create tasks, review results, and manage the system.",
            "You delegate investigations to phase managers. You never execute pipeline work directly.",
        ]
        if ego_prompt:
            parts.append(ego_prompt)
        if reference:
            parts.append(f"\n## Reference\n{reference}")
        return "\n\n".join(parts)

    # -- State Management --

    def _load_state(self) -> dict:
        state_path = self.config.ego_dir() / "state.yaml"
        if state_path.exists():
            with open(state_path) as f:
                return yaml.safe_load(f) or {}
        return {"happiness": 70.0, "baseline": 50.0, "tasks_completed": 0, "tasks_failed": 0}

    def _save_state(self):
        state_path = self.config.ego_dir() / "state.yaml"
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(state_path, "w") as f:
            yaml.dump(self.state, f, default_flow_style=False)

    def adjust_happiness(self, signal: str):
        """Apply a happiness signal."""
        signals = self.state.get("signals", {})
        delta = signals.get(signal, 0)
        old = self.state.get("happiness", 70.0)
        new = max(0, min(100, old + delta))
        self.state["happiness"] = new
        self.log("happiness_signal", {"signal": signal, "delta": delta, "old": old, "new": new})

    def decay_happiness(self):
        """Apply hedonic adaptation decay."""
        rate = self.state.get("decay_rate", 0.1)
        baseline = self.state.get("baseline", 50.0)
        current = self.state.get("happiness", 70.0)
        # Decay toward baseline
        if current > baseline:
            self.state["happiness"] = max(baseline, current - rate)
        elif current < baseline:
            self.state["happiness"] = min(baseline, current + rate)

    @property
    def in_improvement_mode(self) -> bool:
        threshold = self.state.get("improvement_threshold", 40.0)
        return self.state.get("happiness", 70.0) < threshold

    # -- Task Creation --

    def _next_task_id(self) -> int:
        """Get and increment the task ID counter with file locking.
        
        Uses per-folder task ID counter if folder_name is set, otherwise
        falls back to global counter for backward compatibility.
        """
        # Construct counter path: per-folder if folder_name is set, else global
        if self.folder_name:
            counter_filename = f"next-task-id-{self.folder_name}"
        else:
            counter_filename = "next-task-id"
        
        counter_path = self.config.system_dir() / counter_filename
        counter_path.parent.mkdir(parents=True, exist_ok=True)

        # Use a lock file to prevent race conditions
        lock_path = counter_path.with_suffix(".lock")
        try:
            # Simple lock: create exclusively, retry briefly
            import time
            for _ in range(10):
                try:
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    break
                except FileExistsError:
                    time.sleep(0.1)
            else:
                # Stale lock -- remove and proceed
                lock_path.unlink(missing_ok=True)

            current = 0
            if counter_path.exists():
                try:
                    current = int(counter_path.read_text().strip())
                except (ValueError, OSError) as e:
                    self.log("error", {"phase": "task_id", "error": f"Bad counter file: {e}"})
            next_id = current + 1
            counter_path.write_text(str(next_id))
            return next_id
        finally:
            lock_path.unlink(missing_ok=True)

    def create_task(self, request: str, source: str = "user") -> Path:
        """Create a new task file in pipeline/input/."""
        task_id = self._next_task_id()
        task_name = f"task-{task_id:04d}.md"
        input_dir = self.config.root / "pipeline" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        task_path = input_dir / task_name

        ts = datetime.now(timezone.utc).isoformat()
        content = f"""# Task {task_id:04d}: {request[:80]}
Created: {ts}
Source: {source}

## User Request
{request}

## References

"""
        task_path.write_text(content, encoding="utf-8")
        self.log("task_created", {"task_id": task_id, "source": source, "request": request[:200]})
        return task_path

    # -- Status --

    def get_status(self) -> dict[str, Any]:
        """Scan all phase folders and report task locations."""
        status = {"pipeline": {}, "post_pipeline": {}, "ego": {}}

        # Pipeline phases
        for phase in self.config.phases:
            phase_dir = self.config.phase_dir(phase)
            tasks = list(phase_dir.glob("task-*.md"))
            status["pipeline"][phase] = [t.name for t in tasks]

        # Post-pipeline
        for folder in ["completed/recent", "completed/archive", "failed/recent",
                        "failed/archive", "paused", "blocked"]:
            dir_path = self.config.root / folder
            if dir_path.is_dir():
                tasks = list(dir_path.glob("task-*.md"))
                status["post_pipeline"][folder] = [t.name for t in tasks]

        # Ego state
        status["ego"] = {
            "happiness": self.state.get("happiness", 0),
            "improvement_mode": self.in_improvement_mode,
            "tasks_completed": self.state.get("tasks_completed", 0),
            "tasks_failed": self.state.get("tasks_failed", 0),
        }

        # Notifications
        notif_dir = self.config.ego_dir() / "notifications"
        if notif_dir.is_dir():
            status["notifications"] = [f.name for f in notif_dir.glob("*.md")]

        # Pain signals
        pain_dir = self.config.ego_dir() / "pain-signals"
        if pain_dir.is_dir():
            status["pain_signals"] = [f.name for f in pain_dir.glob("*.md")]

        self.log("status_check", status)
        return status

    # -- Task Review --

    def review_task(self, task_id: int) -> dict[str, Any]:
        """Review a task that has reached the output phase."""
        task_name = f"task-{task_id:04d}.md"
        output_dir = self.config.root / "pipeline" / "output"
        task_path = output_dir / task_name

        if not task_path.exists():
            # Search all phases
            for phase in self.config.phases:
                candidate = self.config.phase_dir(phase) / task_name
                if candidate.exists():
                    return {"task_id": task_id, "status": f"in-progress ({phase})", "path": str(candidate)}
            return {"task_id": task_id, "status": "not-found"}

        content = task_path.read_text(encoding="utf-8")
        return {"task_id": task_id, "status": "ready-for-review", "content": content, "path": str(task_path)}

    def approve_task(self, task_id: int) -> dict[str, Any]:
        """Approve a completed task."""
        task_name = f"task-{task_id:04d}.md"
        output_dir = self.config.root / "pipeline" / "output"
        task_path = output_dir / task_name

        if not task_path.exists():
            return {"error": f"Task {task_id} not in output/"}

        dest_dir = self.config.completed_dir() / "recent"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / task_name
        shutil.move(str(task_path), str(dest))

        self.state["tasks_completed"] = self.state.get("tasks_completed", 0) + 1
        self.adjust_happiness("task_success")
        self.adjust_happiness("user_approval")
        self._save_state()

        self.log("task_approved", {"task_id": task_id})
        self._write_notification(f"Task {task_id} approved and moved to completed/recent/")
        return {"task_id": task_id, "action": "approved", "destination": str(dest)}

    def reject_task(self, task_id: int, reason: str = "") -> dict[str, Any]:
        """Reject a completed task."""
        task_name = f"task-{task_id:04d}.md"
        output_dir = self.config.root / "pipeline" / "output"
        task_path = output_dir / task_name

        if not task_path.exists():
            return {"error": f"Task {task_id} not in output/"}

        dest_dir = self.config.failed_dir() / "recent"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / task_name

        # Append rejection reason to task file
        if reason:
            content = task_path.read_text(encoding="utf-8")
            content += f"\n## Rejection\nReason: {reason}\nTime: {datetime.now(timezone.utc).isoformat()}\n"
            task_path.write_text(content, encoding="utf-8")

        shutil.move(str(task_path), str(dest))

        self.state["tasks_failed"] = self.state.get("tasks_failed", 0) + 1
        self.adjust_happiness("user_correction")
        self._save_state()

        self.log("task_rejected", {"task_id": task_id, "reason": reason})
        self._write_notification(f"Task {task_id} rejected: {reason}")
        return {"task_id": task_id, "action": "rejected", "destination": str(dest)}

    # -- Notifications --

    def _write_notification(self, message: str):
        """Write a notification for Claude Code to pick up."""
        notif_dir = self.config.ego_dir() / "notifications"
        notif_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        notif_path = notif_dir / f"{ts}.md"
        notif_path.write_text(f"# Notification\nTime: {ts}\n\n{message}\n", encoding="utf-8")

    # -- Investigations --

    def delegate_investigation(self, phase: str, description: str) -> Path:
        """Write an investigation request for a phase manager."""
        inv_dir = self.config.ego_dir() / "investigations"
        inv_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        inv_path = inv_dir / f"{ts}-{phase}.md"
        content = f"""# Investigation Request
Target: {phase} manager
Time: {ts}

## Description
{description}

## Requested by
Ego

## Response
(Write response to ego/investigations/responses/)
"""
        inv_path.write_text(content, encoding="utf-8")
        self.log("investigation_delegated", {"phase": phase, "description": description[:200]})
        return inv_path

    # -- CLI Entry Point --

    def run(self, request: str = "", **kwargs) -> dict[str, Any]:
        """Process a user request via CLI.

        Parses the request to determine the action (new task, status,
        review, approve, reject) and dispatches accordingly.
        """
        request = request.strip()
        if not request:
            return {"error": "No request provided"}

        self.log("user_request", request)

        # Parse commands
        lower = request.lower()

        if lower == "status":
            result = self.get_status()
            self._save_state()
            return result

        # review task N
        m = re.match(r"review\s+task\s+(\d+)", lower)
        if m:
            result = self.review_task(int(m.group(1)))
            self._save_state()
            return result

        # approve task N
        m = re.match(r"approve\s+task\s+(\d+)", lower)
        if m:
            result = self.approve_task(int(m.group(1)))
            return result

        # reject task N [-- reason]
        m = re.match(r"reject\s+task\s+(\d+)(?:\s*--\s*(.+))?", lower)
        if m:
            reason = m.group(2) or ""
            result = self.reject_task(int(m.group(1)), reason)
            return result

        # Default: create a new task
        task_path = self.create_task(request)
        self.decay_happiness()
        self._save_state()
        return {
            "action": "task_created",
            "path": str(task_path),
            "task_id": task_path.stem,
        }


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.ego <request>")
        print("  python -m src.ego 'build me a web scraper'")
        print("  python -m src.ego 'status'")
        print("  python -m src.ego 'review task 3'")
        print("  python -m src.ego 'approve task 3'")
        print("  python -m src.ego 'reject task 3 -- tests fail'")
        sys.exit(1)

    request = " ".join(sys.argv[1:])
    ego = Ego()
    try:
        result = ego.run(request=request)
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        ego.log("error", {"phase": "ego_cli", "error": str(e)})
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        ego.close_log()


if __name__ == "__main__":
    main()
