#!/usr/bin/env python3
"""Neural Pipeline TUI -- thin shell around Ego.

Every message is a task. On startup, scans pipeline for unfinished tasks
from this project and resumes them. Conversation history reconstructed
from ego JSONL logs -- no separate session files.

Synchronous. Ctrl+C kills everything.

Usage:
  python tui.py
  python tui.py "add dark mode to the todo app"
"""
import json
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# -- Interrupt handling --
# First Ctrl+C kills the active shell command (if any) or interrupts the API call.
# Second Ctrl+C within 2 seconds exits the TUI.

_interrupted = False
_interrupt_time = 0.0


def _sigint_handler(sig, frame):
    global _interrupted, _interrupt_time

    now = time.monotonic()

    # If we already interrupted recently (within 2s), exit for real
    if _interrupted and (now - _interrupt_time) < 2.0:
        print("\n[exiting]")
        sys.exit(1)

    _interrupted = True
    _interrupt_time = now

    # Try to kill active shell subprocess first
    try:
        if kill_active_shell():
            print("\n  [interrupted command]")
            return
    except Exception:
        pass

    print("\n  [interrupted -- press Ctrl+C again within 2s to exit]")


# -- Bootstrap --

PIPELINE_ROOT = Path(__file__).resolve().parent
CWD = Path.cwd().resolve()
sys.path.insert(0, str(PIPELINE_ROOT))

from src.agent_base import sanitize_messages
from src.config import Config
from src.ego import Ego
from src.tools import TOOL_SCHEMAS, execute_tool, set_allowed_roots, kill_active_shell

# Register signal handler after imports so kill_active_shell is available
signal.signal(signal.SIGINT, _sigint_handler)

cfg = Config()
set_allowed_roots([CWD])

# Build system prompt with project context
def build_system_prompt():
    base = """You are a coding assistant with filesystem tools.
You can read, write, edit files, run shell commands, and search codebases.
Be direct. Do the work. Show results."""

    claude_md = CWD / "CLAUDE.md"
    if claude_md.exists():
        try:
            ctx = claude_md.read_text(encoding="utf-8")[:4000]
            base += f"\n\n## Project Context (from CLAUDE.md)\n{ctx}"
        except Exception:
            pass

    base += f"\n\nWorking directory: {CWD}"
    return base

# Initialize ego with CWD-aware system prompt and tools
ego = Ego(config=cfg, folder_name=CWD.name)
ego.system_prompt = build_system_prompt()
ego.tools = TOOL_SCHEMAS

# -- Monitor log tailing --
# Normal mode: drain between loop iterations (conscious attention in the gaps).
# Pain mode (improvement_mode): background thread for real-time visibility (hypervigilance).

_MONITOR_EVENTS = {"task_routed", "task_detected", "manager_spawned", "manager_started",
                   "manager_spawn_error", "pain_signal_sent", "stuck_task"}


class MonitorTail:
    """Tails the monitor JSONL log for pipeline activity."""

    def __init__(self):
        self._log_path: Path | None = None
        self._offset: int = 0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._find_log()

    def _find_log(self):
        """Find the most recent monitor log file."""
        log_dir = cfg.monitor_dir() / "logs"
        if not log_dir.is_dir():
            return
        logs = sorted(log_dir.glob("*-monitor.jsonl"), reverse=True)
        if logs:
            self._log_path = logs[0]
            # Start from end of file (only show new events)
            try:
                self._offset = self._log_path.stat().st_size
            except OSError:
                self._offset = 0

    def drain(self) -> list[str]:
        """Read new monitor events since last check. Returns formatted lines."""
        if not self._log_path or not self._log_path.exists():
            self._find_log()
            if not self._log_path:
                return []

        lines = []
        try:
            size = self._log_path.stat().st_size
            if size <= self._offset:
                if size < self._offset:
                    # Log rotated -- find new log
                    self._find_log()
                return []

            with open(self._log_path, "r", encoding="utf-8") as f:
                f.seek(self._offset)
                raw = f.read()
                self._offset = f.tell()

            for line in raw.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    fmt = self._format_event(record)
                    if fmt:
                        lines.append(fmt)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        return lines

    def _format_event(self, record: dict) -> str | None:
        """Format a monitor log record for display. Returns None to skip."""
        rtype = record.get("type", "")
        if rtype not in _MONITOR_EVENTS:
            return None

        content = record.get("content", {})

        if rtype == "task_routed":
            return f"  [pipeline] {content.get('task', '?')}: {content.get('from', '?')} -> {content.get('to', '?')}"
        if rtype == "task_detected":
            return f"  [pipeline] {content.get('task', '?')} arrived in {content.get('phase', '?')}"
        if rtype == "manager_spawned":
            return f"  [pipeline] {content.get('phase', '?')} manager starting for {content.get('task', '?')}"
        if rtype == "stuck_task":
            return f"  [pipeline] {content.get('task', '?')} stuck in {content.get('phase', '?')} ({content.get('age_minutes', 0):.0f}m)"
        if rtype == "pain_signal_sent":
            return f"  [pipeline] pain signal: {content.get('type', '?')}"
        if rtype == "manager_spawn_error":
            return f"  [pipeline] manager spawn failed: {content.get('error', '?')}"

        return None

    def print_updates(self):
        """Drain and print any new monitor events."""
        for line in self.drain():
            print(line)

    # -- Pain mode: background thread --

    def start_live(self):
        """Start background thread that prints monitor events in real time."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._live_loop, daemon=True)
        self._thread.start()

    def stop_live(self):
        """Stop the background thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _live_loop(self):
        """Background loop: poll monitor log and print events."""
        while not self._stop_event.is_set():
            try:
                for line in self.drain():
                    print(line, flush=True)
            except Exception:
                pass
            self._stop_event.wait(1.0)


monitor_tail = MonitorTail()


# -- Session reconstruction from ego JSONL logs --

def restore_session():
    """Reconstruct messages array from the latest ego JSONL log for this project.

    Log entries have type "user" or "assistant" with full API message format
    in the content field. Tool results logged separately get matched back."""
    log_dir = cfg.ego_dir() / "logs"
    if not log_dir.is_dir():
        return []

    # Find the most recent log that has TUI conversation entries
    source_tag = f"tui:{CWD.name}"
    logs = sorted(log_dir.glob("*-ego.jsonl"), reverse=True)

    for log_path in logs:
        messages = []
        has_tui_entries = False
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    rtype = record.get("type")

                    # task_created with our source tag means this log is ours
                    if rtype == "task_created":
                        content = record.get("content", {})
                        if isinstance(content, dict) and source_tag in str(content.get("source", "")):
                            has_tui_entries = True

                    # Reconstruct messages from user/assistant entries
                    if rtype == "user":
                        content = record.get("content")
                        if isinstance(content, dict) and "role" in content:
                            # Full API message format
                            messages.append(content)
                        elif isinstance(content, str) and content:
                            messages.append({"role": "user", "content": content})

                    elif rtype == "assistant":
                        content = record.get("content")
                        if isinstance(content, dict) and "role" in content:
                            # Full API message format
                            messages.append(content)

                    elif rtype == "tool_result":
                        # Individual tool results logged separately -- skip,
                        # they're already captured in the "user" messages above.
                        pass

        except Exception:
            continue

        if has_tui_entries and messages:
            # Deduplicate consecutive identical user messages (from old logs
            # that had the double-logging bug)
            deduped = []
            for msg in messages:
                if deduped and msg == deduped[-1]:
                    continue
                deduped.append(msg)
            return _sanitize_messages(deduped)

    return []


def _sanitize_messages(messages):
    """Delegate to the shared sanitizer in agent_base."""
    return sanitize_messages(messages)


# -- Task file lookup --

def _find_task_file(task_name: str) -> Path | None:
    """Find a task file across all pipeline phase dirs (it may have moved)."""
    for phase in list(cfg.phases) + ["output"]:
        candidate = cfg.root / "pipeline" / phase / task_name
        if candidate.exists():
            return candidate
    # Also check input
    candidate = cfg.root / "pipeline" / "input" / task_name
    if candidate.exists():
        return candidate
    return None


# -- Task scanning --

def find_pending_tasks():
    """Scan all pipeline phases for tasks from this project.
    Returns list of (phase, task_path) for unfinished tasks."""
    source_tag = f"tui:{CWD.name}"
    pending = []
    for phase in cfg.phases:
        phase_dir = cfg.root / "pipeline" / phase
        if not phase_dir.is_dir():
            continue
        for task_file in sorted(phase_dir.glob("task-*.md")):
            try:
                content = task_file.read_text(encoding="utf-8")
                if source_tag in content:
                    pending.append((phase, task_file))
            except Exception:
                continue
    return pending


# -- Display --

def print_tool_call(name, inp):
    if name == "shell":
        print(f"  $ {inp.get('command', '')}")
    elif name in ("read_file", "write_file", "edit_file"):
        print(f"  [{name}] {inp.get('path', '')}")
    elif name == "search_files":
        print(f"  [search] {inp.get('pattern', '')} in {inp.get('path', '.')}")
    elif name == "list_files":
        print(f"  [ls] {inp.get('pattern', '')}")
    else:
        print(f"  [{name}] {json.dumps(inp)[:80]}")

def print_result(result, max_lines=20):
    lines = result.split("\n")
    for line in lines[:max_lines]:
        print(f"  | {line}")
    if len(lines) > max_lines:
        print(f"  | ... ({len(lines) - max_lines} more lines)")


# -- Agentic loop (shared by chat and resume) --

def run_loop(messages):
    """Drive the tool loop, printing output. Returns response text."""
    global _interrupted
    response_text = []

    # Pain mode: live monitor tailing. Triggered by low happiness OR CCT_DEBUG=1
    pain_mode = ego.in_improvement_mode or os.environ.get("CCT_DEBUG") == "1"
    if pain_mode:
        monitor_tail.start_live()

    while True:
        # Normal mode: check for pipeline updates between iterations
        if not pain_mode:
            monitor_tail.print_updates()

        try:
            response = ego.send_message(messages)
        except KeyboardInterrupt:
            ego.log("interrupted", {"phase": "send_message"})
            print("\n  [API call interrupted -- returning to prompt]")
            _interrupted = False
            break
        except Exception as e:
            ego.log("error", {
                "phase": "send_message",
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            print(f"\n  [error] API call failed: {e}")
            break

        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
                response_text.append(block.text)
                print(block.text)
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
                print_tool_call(block.name, block.input)

        # max_tokens truncation: the last tool_use block is likely incomplete
        # (missing or partial input). Strip it and warn, then let the model retry.
        if response.stop_reason == "max_tokens":
            # Remove any tool_use blocks -- they may be truncated/incomplete
            text_only = [b for b in assistant_content if b.get("type") != "tool_use"]
            if text_only:
                messages.append({"role": "assistant", "content": text_only})
            print("  [warn] response truncated (max_tokens) -- retrying")
            ego.log("truncated", {"stop_reason": "max_tokens", "stripped_tool_use": len(assistant_content) - len(text_only)})
            # Ask the model to continue with shorter output
            messages.append({"role": "user", "content": "Your previous response was truncated. Continue, but use smaller steps -- one tool call at a time."})
            continue

        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        was_interrupted = False
        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = execute_tool(block.name, block.input, project_root=CWD)
                    ego.log("tool_result", result, tool=block.name)
                except Exception as e:
                    result = f"Error: {e}"
                if result == "[command interrupted]":
                    was_interrupted = True
                print_result(result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        tool_msg = {"role": "user", "content": tool_results}
        messages.append(tool_msg)
        # Note: send_message() already logs messages[-1] on the next iteration,
        # so we don't log tool_msg here to avoid duplicates in JSONL.

        if was_interrupted:
            # Reset interrupt flag so user doesn't accidentally exit
            _interrupted = False
            print("  [task interrupted -- returning to prompt]")
            break

    # Stop live tailing if it was running
    if pain_mode:
        monitor_tail.stop_live()

    # Final drain in case anything came in during the last step
    monitor_tail.print_updates()

    # Reset interrupt flag so returning to prompt doesn't look like a double-tap
    _interrupted = False

    return "".join(response_text)


# -- Chat --

def chat(user_msg, messages):
    """Create task, run agentic loop, write result to pipeline output."""
    try:
        task_path = ego.create_task(user_msg, source=f"tui:{CWD.name}")
        print(f"  [{task_path.stem}]")

        messages.append({"role": "user", "content": user_msg})

        response_text = run_loop(messages)

        # Write result to pipeline output
        # Task file may have been moved by the monitor during execution --
        # search all phase dirs for it.
        output_dir = cfg.root / "pipeline" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / task_path.name

        actual_path = _find_task_file(task_path.name)
        if actual_path:
            task_content = actual_path.read_text(encoding="utf-8")
            if actual_path != output_path and actual_path.exists():
                actual_path.unlink()
        else:
            # Task file gone (monitor moved it) -- reconstruct minimal content
            task_content = f"# {task_path.stem}\nSource: tui:{CWD.name}\n"

        task_content += f"\n## Result\n{response_text}\n"
        output_path.write_text(task_content, encoding="utf-8")

    except Exception as e:
        ego.log("error", {
            "phase": "chat",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        print(f"\n  [error] {e}")

    return messages


def resume_task(task_path, phase, messages):
    """Resume an unfinished task."""
    try:
        content = task_path.read_text(encoding="utf-8")
        task_id = task_path.stem

        if phase == "output":
            # Already done -- inject as context
            messages.append({"role": "user", "content": f"[Previous task {task_id} completed]\n{content}"})
            messages.append({"role": "assistant", "content": [{"type": "text", "text": f"Noted -- {task_id} is done. Ready for next request."}]})
            print(f"  [{task_id}] completed (loaded as context)")
            return messages

        print(f"  [{task_id}] resuming from {phase}/...")
        resume_prompt = (
            f"Unfinished task (interrupted). Task file:\n\n{content}\n\n"
            f"Currently in '{phase}' phase. Continue working on the original request."
        )
        messages.append({"role": "user", "content": resume_prompt})

        response_text = run_loop(messages)

        # Move to output
        output_dir = cfg.root / "pipeline" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / task_path.name
        task_content = task_path.read_text(encoding="utf-8")
        task_content += f"\n## Result\n{response_text}\n"
        output_path.write_text(task_content, encoding="utf-8")
        if task_path.parent != output_dir and task_path.exists():
            task_path.unlink()

        print(f"  [{task_id}] done\n")

    except Exception as e:
        ego.log("error", {
            "phase": "resume_task",
            "task": str(task_path),
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        print(f"\n  [error] resume failed: {e}")

    return messages


def main():
    print("Neural Pipeline TUI")
    print(f"Project: {CWD.name}")
    print("Ctrl+C to quit.\n")

    try:
        # Check monitor health
        heartbeat_path = cfg.monitor_dir() / "health" / "heartbeat"
        if heartbeat_path.exists():
            try:
                last_beat = datetime.fromisoformat(heartbeat_path.read_text().strip())
                age = (datetime.now(timezone.utc) - last_beat).total_seconds()
                if age > 60:
                    print(f"  [warn] monitor heartbeat is {age / 60:.0f}m old -- may be stopped")
            except Exception:
                print("  [warn] could not read monitor heartbeat")
        else:
            print("  [warn] monitor not running (no heartbeat file)")

        # Restore conversation from ego JSONL logs
        try:
            messages = restore_session()
            if messages:
                n = sum(1 for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str))
                print(f"  (restored {n} previous requests from logs)")
        except Exception as e:
            ego.log("error", {"phase": "restore_session", "error": str(e), "traceback": traceback.format_exc()})
            print(f"  [warn] Could not restore session: {e}")
            messages = []

        # Resume any pending tasks for this project
        try:
            pending = find_pending_tasks()
            if pending:
                for phase, task_path in pending:
                    messages = resume_task(task_path, phase, messages)
        except Exception as e:
            ego.log("error", {"phase": "find_pending", "error": str(e), "traceback": traceback.format_exc()})
            print(f"  [warn] Could not scan pending tasks: {e}")

        # One-shot mode
        if len(sys.argv) > 1:
            request = " ".join(sys.argv[1:])
            print(f"> {request}\n")
            chat(request, messages)
            return

        # Interactive loop
        while True:
            global _interrupted
            monitor_tail.print_updates()
            _interrupted = False  # Reset at prompt
            try:
                user_input = input("> ").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                # Single Ctrl+C at prompt -- just print newline, stay in loop
                # Double Ctrl+C is handled by _sigint_handler -> sys.exit(1)
                print()
                continue

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if user_input.lower() == "status":
                try:
                    status = ego.get_status()
                    print(json.dumps(status, indent=2, default=str))
                except Exception as e:
                    ego.log("error", {"phase": "status", "error": str(e)})
                    print(f"  [error] {e}")
                print()
                continue
            if user_input.lower() == "new":
                messages = []
                print("  Session cleared.\n")
                continue

            print()
            chat(user_input, messages)
            print()

    finally:
        ego.close_log()


if __name__ == "__main__":
    main()
