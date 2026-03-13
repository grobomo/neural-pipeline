"""Monitor daemon for Neural Pipeline.

The autonomic nervous system. Uses watchdog for filesystem event detection.
Watches phase folders for task arrivals, spawns managers, runs health checks,
and flags anomalies to the ego.

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
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

from .agent_base import AgentBase
from .config import Config


class PipelineEventHandler(FileSystemEventHandler):
    """Handles filesystem events in pipeline phase folders."""

    def __init__(self, monitor: "Monitor"):
        self.monitor = monitor

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.name.startswith("task-") and path.suffix == ".md":
            self.monitor.on_task_arrived(path)

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        if dest.name.startswith("task-") and dest.suffix == ".md":
            self.monitor.on_task_arrived(dest)


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

    def on_task_arrived(self, task_path: Path):
        """Called when a task file appears in a phase folder."""
        try:
            # Determine which phase this is
            phase = task_path.parent.name
            pipeline_phases = self.config.pipeline_phases

            # Input phase: move task to first processing phase (why)
            if phase == "input":
                self.log("task_detected", {"phase": "input", "task": task_path.name})
                why_dir = self.config.phase_dir("why")
                why_dir.mkdir(parents=True, exist_ok=True)
                import shutil
                dest = why_dir / task_path.name
                if not task_path.exists():
                    self.log("task_already_moved", {"task": task_path.name})
                    return
                shutil.move(str(task_path), str(dest))
                self.log("task_routed", {"from": "input", "to": "why", "task": task_path.name})
                self.spawn_manager("why", dest)
                return

            if phase not in pipeline_phases:
                self.log("event_ignored", {"path": str(task_path), "reason": f"not a processing phase: {phase}"})
                return

            self.log("task_detected", {"phase": phase, "task": task_path.name})
            self.spawn_manager(phase, task_path)
        except Exception as e:
            self.log("error", {
                "phase": "on_task_arrived",
                "task": str(task_path),
                "error": str(e),
            })
            self.flag_pain_signal("task-routing-failed", f"Failed to route {task_path.name}: {e}")

    def spawn_manager(self, phase: str, task_path: Path):
        """Spawn a manager subprocess for a phase."""
        cmd = [
            sys.executable, "-m", "src.manager_runner",
            "--phase", phase,
            "--task", str(task_path),
            "--root", str(self.config.root),
        ]
        self.log("manager_spawned", {"phase": phase, "task": task_path.name, "cmd": " ".join(cmd)})

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
            self.flag_pain_signal("manager-spawn-failed", f"Could not spawn {phase} manager: {e}")

    def flag_pain_signal(self, signal_type: str, description: str):
        """Write a pain signal to ego/pain-signals/."""
        pain_dir = self.config.ego_dir() / "pain-signals"
        pain_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        pain_path = pain_dir / f"{ts}-monitor-{signal_type}.md"
        content = f"""# Pain Signal: {signal_type}
Source: monitor
Time: {ts}

## Description
{description}
"""
        pain_path.write_text(content, encoding="utf-8")
        self.log("pain_signal_sent", {"type": signal_type})

    def write_heartbeat(self):
        """Update the heartbeat file."""
        try:
            heartbeat = self.health_dir / "heartbeat"
            heartbeat.write_text(datetime.now(timezone.utc).isoformat())
        except Exception as e:
            self.log("error", {"phase": "heartbeat", "error": str(e)})

    def check_stuck_tasks(self):
        """Check for tasks stuck too long in a phase."""
        threshold_minutes = self.config.threshold("stuck_task_minutes")
        now = datetime.now(timezone.utc)

        for phase in self.config.pipeline_phases:
            phase_dir = self.config.phase_dir(phase)
            for task_file in phase_dir.glob("task-*.md"):
                # Check file modification time
                import os
                mtime = datetime.fromtimestamp(os.path.getmtime(task_file), tz=timezone.utc)
                age_minutes = (now - mtime).total_seconds() / 60

                if age_minutes > threshold_minutes:
                    self.log("stuck_task", {
                        "phase": phase,
                        "task": task_file.name,
                        "age_minutes": round(age_minutes, 1),
                    })
                    self.flag_pain_signal(
                        "stuck-task",
                        f"Task {task_file.name} stuck in {phase} for {age_minutes:.0f} minutes",
                    )

    def check_health(self):
        """Run all health checks and write results."""
        health = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phases": {},
        }
        for phase in self.config.pipeline_phases:
            phase_dir = self.config.phase_dir(phase)
            tasks = list(phase_dir.glob("task-*.md"))
            pending = list((phase_dir / "workers" / "steps" / "pending").glob("*.md")) if (phase_dir / "workers" / "steps" / "pending").is_dir() else []
            active = list((phase_dir / "workers" / "steps" / "active").glob("*.md")) if (phase_dir / "workers" / "steps" / "active").is_dir() else []
            health["phases"][phase] = {
                "tasks": len(tasks),
                "pending_steps": len(pending),
                "active_steps": len(active),
            }

        health_path = self.health_dir / "latest.yaml"
        with open(health_path, "w") as f:
            yaml.dump(health, f, default_flow_style=False)

        self.log("health_check", health)

    def scan_for_existing_tasks(self):
        """On startup, scan input/ and phase folders for tasks (crash recovery)."""
        # Scan input/ first -- tasks here need routing to why/
        input_dir = self.config.root / "pipeline" / "input"
        if input_dir.is_dir():
            for task_file in input_dir.glob("task-*.md"):
                self.log("existing_task_found", {"phase": "input", "task": task_file.name})
                self.on_task_arrived(task_file)

        for phase in self.config.pipeline_phases:
            phase_dir = self.config.phase_dir(phase)
            for task_file in phase_dir.glob("task-*.md"):
                self.log("existing_task_found", {"phase": phase, "task": task_file.name})
                self.spawn_manager(phase, task_file)

    def run(self, **kwargs):
        """Start the monitor daemon."""
        self.log("monitor_start", {"root": str(self.config.root)})
        self._running = True
        
        # Write PID file
        pid_file = Path(".tmp") / "monitor.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        # Set up watchdog observers for each phase folder
        handler = PipelineEventHandler(self)
        for phase in self.config.pipeline_phases:
            phase_dir = self.config.phase_dir(phase)
            phase_dir.mkdir(parents=True, exist_ok=True)
            self.observer.schedule(handler, str(phase_dir), recursive=False)
            self.log("watching", {"phase": phase, "path": str(phase_dir)})

        # Also watch input/ for tasks that need to be moved to why/
        input_dir = self.config.root / "pipeline" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(handler, str(input_dir), recursive=False)

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
        # Override config to use specified root
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
