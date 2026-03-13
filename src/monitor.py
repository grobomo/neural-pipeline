"""Monitor daemon for Neural Pipeline.

The autonomic nervous system. Uses watchdog for filesystem event detection.
Watches per-project phase folders for task arrivals, spawns managers, runs
health checks, and flags anomalies to the ego.

Usage:
  python -m src.monitor /path/to/project/root
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent, DirCreatedEvent
from watchdog.observers import Observer

from .agent_base import AgentBase
from .config import Config


class PipelineEventHandler(FileSystemEventHandler):
    """Handles filesystem events in pipeline phase folders."""

    def __init__(self, monitor: "Monitor"):
        self.monitor = monitor

    def _is_pipeline_file(self, name: str) -> bool:
        return name.endswith(".md") and (name.startswith("task-") or name.startswith("pain-"))

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._is_pipeline_file(path.name):
            self.monitor.on_task_arrived(path)

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        if self._is_pipeline_file(dest.name):
            self.monitor.on_task_arrived(dest)


class ProjectDiscoveryHandler(FileSystemEventHandler):
    """Watches pipeline/projects/ for new project directories."""

    def __init__(self, monitor: "Monitor"):
        self.monitor = monitor

    def on_created(self, event):
        if not event.is_directory:
            return
        project_dir = Path(event.src_path)
        # Only handle direct children of pipeline/projects/
        if project_dir.parent == self.monitor._projects_root:
            self.monitor.watch_project(project_dir)


class Monitor(AgentBase):
    """Background daemon that watches the pipeline and keeps it running."""

    def __init__(self, config: Config | None = None):
        cfg = config or Config()
        log_dir = cfg.monitor_dir() / "logs"

        super().__init__(
            role="monitor",
            log_dir=log_dir,
            config=cfg,
            system_prompt="Monitor daemon -- autonomic nervous system.",
        )
        self.observer = Observer()
        self.health_dir = cfg.monitor_dir() / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._projects_root = cfg.root / "pipeline" / "projects"
        self._watched_projects: set[str] = set()  # slugs we're already watching

    def _extract_project_slug(self, task_path: Path) -> str | None:
        """Extract project slug from a task path.

        Expected: pipeline/projects/{slug}/{phase}/task-NNNN.md
        So parent is phase dir, grandparent is project dir.
        """
        phase_dir = task_path.parent
        project_dir = phase_dir.parent
        if project_dir.parent == self._projects_root:
            return project_dir.name
        return None

    def on_task_arrived(self, task_path: Path):
        """Called when a task file appears in a phase folder."""
        try:
            phase = task_path.parent.name
            slug = self._extract_project_slug(task_path)
            pipeline_phases = self.config.pipeline_phases

            if phase == "input":
                self.log("task_detected", {"phase": "input", "task": task_path.name, "project": slug or "?"})
                # Route to why/ within the same project dir
                project_dir = task_path.parent.parent
                why_dir = project_dir / "why"
                why_dir.mkdir(parents=True, exist_ok=True)
                import shutil
                dest = why_dir / task_path.name
                if not task_path.exists():
                    self.log("task_already_moved", {"task": task_path.name})
                    return
                shutil.move(str(task_path), str(dest))
                self.log("task_routed", {"from": "input", "to": "why", "task": task_path.name, "project": slug or "?"})
                self.spawn_manager("why", dest, slug)
                return

            if phase not in pipeline_phases:
                self.log("event_ignored", {"path": str(task_path), "reason": f"not a processing phase: {phase}"})
                return

            self.log("task_detected", {"phase": phase, "task": task_path.name, "project": slug or "?"})
            self.spawn_manager(phase, task_path, slug)
        except Exception as e:
            self.log("error", {
                "phase": "on_task_arrived",
                "task": str(task_path),
                "error": str(e),
            })
            slug = self._extract_project_slug(task_path)
            self.flag_pain_signal("task-routing-failed", f"Failed to route {task_path.name}: {e}", slug)

    def spawn_manager(self, phase: str, task_path: Path, project_slug: str | None = None):
        """Spawn a manager subprocess for a phase."""
        cmd = [
            sys.executable, "-m", "src.manager_runner",
            "--phase", phase,
            "--task", str(task_path),
            "--root", str(self.config.root),
        ]
        if project_slug:
            cmd.extend(["--project-slug", project_slug])

        self.log("manager_spawned", {"phase": phase, "task": task_path.name, "project": project_slug or "?", "cmd": " ".join(cmd)})

        try:
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "cwd": str(self.config.root),
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.Popen(cmd, **kwargs)
            self.log("manager_started", {"phase": phase, "pid": result.pid})
        except Exception as e:
            self.log("manager_spawn_error", {"phase": phase, "error": str(e)})
            self.flag_pain_signal("manager-spawn-failed", f"Could not spawn {phase} manager: {e}", project_slug)

    def flag_pain_signal(self, signal_type: str, description: str, project_slug: str | None = None):
        """Create a pain file in the project's input/ dir.

        Pain flows through the normal pipeline (why -> scope -> plan ->
        execute -> verify -> output). Managers detect pain-*.md files and
        use diagnostic prompts instead of implementation prompts.

        Drops happiness immediately by the signal's severity.
        """
        severity = self.config.pain_severity(signal_type)

        # Pain enters the pipeline normally via input/
        if project_slug:
            input_dir = self._projects_root / project_slug / "input"
            project_dir = self._projects_root / project_slug
        else:
            input_dir = self.config.root / "pipeline" / "input"
            project_dir = self.config.root / "pipeline"
        input_dir.mkdir(parents=True, exist_ok=True)

        # Pain compounds -- no dedup. Each cycle creates a new file.
        ts = datetime.now(timezone.utc).isoformat()
        pain_id = self._next_pain_id(project_dir)
        pain_name = f"pain-{pain_id:04d}.md"
        pain_path = input_dir / pain_name

        content = f"""# Pain {pain_id:04d}: {signal_type}
Created: {ts}
Source: monitor
Project: {project_slug or 'unknown'}
Type: {signal_type}
Severity: {severity}

## Description
{description}

## Resolution Required
Fix the root cause and provide evidence. Severity: {severity}.
Reward on verified fix: +{severity * 1.5:.1f} happiness.
"""
        pain_path.write_text(content, encoding="utf-8")

        # Drop happiness immediately
        self._apply_pain_to_happiness(severity)

        self.log("pain_signal_sent", {
            "type": signal_type,
            "description": description,
            "severity": severity,
            "pain": pain_name,
        })

    def _next_pain_id(self, project_dir: Path) -> int:
        """Get next pain ID by scanning existing pain files across all phases."""
        max_id = 0
        for phase_dir in project_dir.iterdir():
            if not phase_dir.is_dir():
                continue
            for f in phase_dir.glob("pain-*.md"):
                try:
                    num = int(f.stem.split("-")[1])
                    max_id = max(max_id, num)
                except (IndexError, ValueError):
                    continue
        return max_id + 1

    def _apply_pain_to_happiness(self, severity: int):
        """Decrease ego happiness by pain severity."""
        try:
            state_path = self.config.ego_dir() / "state.yaml"
            if state_path.exists():
                with open(state_path) as f:
                    state = yaml.safe_load(f) or {}
            else:
                state = {"happiness": 70.0}

            old = state.get("happiness", 70.0)
            state["happiness"] = max(0, old - severity)
            state["last_updated"] = datetime.now(timezone.utc).isoformat()

            with open(state_path, "w") as f:
                yaml.dump(state, f, default_flow_style=False)

            self.log("happiness_pain", {"old": old, "new": state["happiness"], "severity": severity})
        except Exception as e:
            self.log("error", {"phase": "pain_happiness", "error": str(e)})

    def write_heartbeat(self):
        """Update the heartbeat file."""
        try:
            heartbeat = self.health_dir / "heartbeat"
            heartbeat.write_text(datetime.now(timezone.utc).isoformat())
        except Exception as e:
            self.log("error", {"phase": "heartbeat", "error": str(e)})

    def watch_project(self, project_dir: Path):
        """Set up watchers for all phase dirs in a project."""
        slug = project_dir.name
        if slug in self._watched_projects:
            return

        handler = PipelineEventHandler(self)
        for phase in self.config.pipeline_phases:
            phase_dir = project_dir / phase
            phase_dir.mkdir(parents=True, exist_ok=True)
            self.observer.schedule(handler, str(phase_dir), recursive=False)

        # Watch input/ too
        input_dir = project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(handler, str(input_dir), recursive=False)

        self._watched_projects.add(slug)
        self.log("watching_project", {"slug": slug, "path": str(project_dir)})

    def check_stuck_tasks(self):
        """Check for tasks stuck too long in a phase across all projects."""
        threshold_minutes = self.config.threshold("stuck_task_minutes")
        now = datetime.now(timezone.utc)

        for project_dir in self.config.all_project_dirs():
            slug = project_dir.name
            for phase in self.config.pipeline_phases:
                phase_dir = project_dir / phase
                if not phase_dir.is_dir():
                    continue
                for task_file in phase_dir.glob("task-*.md"):
                    mtime = datetime.fromtimestamp(os.path.getmtime(task_file), tz=timezone.utc)
                    age_minutes = (now - mtime).total_seconds() / 60

                    if age_minutes > threshold_minutes:
                        self.log("stuck_task", {
                            "phase": phase,
                            "task": task_file.name,
                            "project": slug,
                            "age_minutes": round(age_minutes, 1),
                        })
                        self.flag_pain_signal(
                            "stuck-task",
                            f"Task {task_file.name} stuck in {phase} for {age_minutes:.0f} minutes",
                            slug,
                        )

    def check_health(self):
        """Run all health checks and write results."""
        health = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "projects": {},
        }
        for project_dir in self.config.all_project_dirs():
            slug = project_dir.name
            project_health = {}
            for phase in self.config.pipeline_phases:
                phase_dir = project_dir / phase
                if not phase_dir.is_dir():
                    project_health[phase] = {"tasks": 0}
                    continue
                tasks = list(phase_dir.glob("task-*.md"))
                pending = list((phase_dir / "workers" / "steps" / "pending").glob("*.md")) if (phase_dir / "workers" / "steps" / "pending").is_dir() else []
                active = list((phase_dir / "workers" / "steps" / "active").glob("*.md")) if (phase_dir / "workers" / "steps" / "active").is_dir() else []
                project_health[phase] = {
                    "tasks": len(tasks),
                    "pending_steps": len(pending),
                    "active_steps": len(active),
                }
            health["projects"][slug] = project_health

        health_path = self.health_dir / "latest.yaml"
        with open(health_path, "w") as f:
            yaml.dump(health, f, default_flow_style=False)

        self.log("health_check", health)

    def scan_for_existing_tasks(self):
        """On startup, scan all project dirs for tasks (crash recovery)."""
        for project_dir in self.config.all_project_dirs():
            slug = project_dir.name

            # Scan input/ first
            input_dir = project_dir / "input"
            if input_dir.is_dir():
                for task_file in input_dir.glob("task-*.md"):
                    self.log("existing_task_found", {"phase": "input", "task": task_file.name, "project": slug})
                    self.on_task_arrived(task_file)

            for phase in self.config.pipeline_phases:
                phase_dir = project_dir / phase
                if not phase_dir.is_dir():
                    continue
                for task_file in phase_dir.glob("task-*.md"):
                    self.log("existing_task_found", {"phase": phase, "task": task_file.name, "project": slug})
                    self.spawn_manager(phase, task_file, slug)

    def run(self, **kwargs):
        """Start the monitor daemon."""
        self.log("monitor_start", {"root": str(self.config.root)})
        self._running = True

        # Write PID file
        pid_file = Path(".tmp") / "monitor.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        # Ensure projects root exists
        self._projects_root.mkdir(parents=True, exist_ok=True)

        # Watch for new project directories
        discovery_handler = ProjectDiscoveryHandler(self)
        self.observer.schedule(discovery_handler, str(self._projects_root), recursive=False)
        self.log("watching_projects_root", {"path": str(self._projects_root)})

        # Set up watchers for all existing project dirs
        for project_dir in self.config.all_project_dirs():
            self.watch_project(project_dir)

        self.observer.start()
        self.log("observer_started", {})

        # Scan for existing tasks (crash recovery)
        self.scan_for_existing_tasks()

        heartbeat_interval = self.config.threshold("monitor_heartbeat_seconds")
        health_check_counter = 0

        try:
            while self._running:
                self.write_heartbeat()
                health_check_counter += 1

                # Health check every 10 heartbeats
                if health_check_counter >= 10:
                    try:
                        self.check_health()
                        self.check_stuck_tasks()
                    except Exception as e:
                        self.log("error", {"phase": "health_check", "error": str(e)})
                    health_check_counter = 0

                time.sleep(heartbeat_interval)
        except KeyboardInterrupt:
            self.log("monitor_stopping", {"reason": "keyboard_interrupt"})
        except Exception as e:
            self.log("error", {"phase": "monitor_loop", "error": str(e)})
        finally:
            self.observer.stop()
            self.observer.join()
            self.log("monitor_stopped", {})
            self.close_log()

    def stop(self):
        """Gracefully stop the monitor."""
        self._running = False


def main():
    """CLI entry point for monitor daemon."""
    root = None
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()

    if root:
        import os
        os.chdir(str(root))

    monitor = Monitor()
    try:
        monitor.run()
    except Exception as e:
        monitor.log("error", {"phase": "monitor_main", "error": str(e)})
        monitor.close_log()
        raise


if __name__ == "__main__":
    main()
