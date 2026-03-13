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
cfg.set_project(CWD)
set_allowed_roots([CWD])
PROJECT_NAME = CWD.name

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
ego = Ego(config=cfg, project_name=PROJECT_NAME, project_path=CWD)
ego.system_prompt = build_system_prompt()
ego.tools = TOOL_SCHEMAS

# -- Monitor log tailing --
# Normal mode: drain between loop iterations (conscious attention in the gaps).
# Pain mode (improvement_mode): background thread for real-time visibility (hypervigilance).

_MONITOR_EVENTS = {"task_routed", "task_detected", "manager_spawned", "manager_started",
                   "manager_spawn_error", "pain_signal_sent", "pain_signal", "stuck_task"}


class MonitorTail:
    """Tails the monitor log and watches task files for phase updates.

    Only shows events for tasks owned by this TUI session (matched by task name).
    Task files grow as each phase appends a ## section -- we show the new content.
    """

    def __init__(self):
        self._log_path: Path | None = None
        self._offset: int = 0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._my_tasks: set[str] = set()  # task filenames created by this session
        self._task_sizes: dict[str, int] = {}  # task_name -> last known file size
        self._find_log()

    def track_task(self, task_name: str):
        """Register a task filename as ours (e.g. 'task-0018.md')."""
        self._my_tasks.add(task_name)
        # Snapshot current size so we only show new content
        task_path = self._find_task(task_name)
        if task_path and task_path.exists():
            try:
                self._task_sizes[task_name] = task_path.stat().st_size
            except OSError:
                self._task_sizes[task_name] = 0
        else:
            self._task_sizes[task_name] = 0

    def _find_task(self, task_name: str) -> Path | None:
        """Locate a task file across all pipeline phases."""
        for phase in list(cfg.phases) + ["output"]:
            candidate = cfg.phase_dir(phase) / task_name
            if candidate.exists():
                return candidate
        return None

    def _drain_task_updates(self) -> list[str]:
        """Check tracked task files for new content appended by phase managers."""
        lines = []
        for task_name in list(self._my_tasks):
            task_path = self._find_task(task_name)
            if not task_path or not task_path.exists():
                continue
            try:
                size = task_path.stat().st_size
                prev = self._task_sizes.get(task_name, 0)
                if size <= prev:
                    continue
                with open(task_path, "r", encoding="utf-8") as f:
                    f.seek(prev)
                    new_content = f.read()
                self._task_sizes[task_name] = size

                # Extract ## headings from the new content to summarize
                for section in new_content.split("\n## "):
                    section = section.strip()
                    if not section:
                        continue
                    heading = section.split("\n", 1)[0].strip("# ").strip()
                    body_lines = section.split("\n")[1:]
                    body = "\n".join(l for l in body_lines if l.strip())
                    if heading and body:
                        lines.append(f"  [{task_name}] {heading}:")
                        for bl in body.strip().splitlines()[:6]:
                            lines.append(f"    {bl}")
                        remaining = len(body.strip().splitlines()) - 6
                        if remaining > 0:
                            lines.append(f"    ... ({remaining} more lines)")
            except OSError:
                pass
        return lines

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
        """Read new monitor events and task file updates. Returns formatted lines."""
        lines = []

        # 1. Monitor log events
        if not self._log_path or not self._log_path.exists():
            self._find_log()

        if self._log_path and self._log_path.exists():
            try:
                size = self._log_path.stat().st_size
                if size < self._offset:
                    self._find_log()
                elif size > self._offset:
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

        # 2. Task file updates (phases appending ## sections)
        lines.extend(self._drain_task_updates())

        return lines

    def _format_event(self, record: dict) -> str | None:
        """Format a monitor log record for display. Returns None to skip."""
        rtype = record.get("type", "")
        if rtype not in _MONITOR_EVENTS:
            return None

        content = record.get("content", {})

        # Filter: only show events for tasks created by this session
        task_name = content.get("task", "")
        if self._my_tasks and task_name and task_name not in self._my_tasks:
            return None

        if rtype == "task_routed":
            return f"  [pipeline] {content.get('task', '?')}: {content.get('from', '?')} -> {content.get('to', '?')}"
        if rtype == "task_detected":
            return f"  [pipeline] {content.get('task', '?')} arrived in {content.get('phase', '?')}"
        if rtype == "manager_spawned":
            return f"  [pipeline] {content.get('phase', '?')} manager starting for {content.get('task', '?')}"
        if rtype == "stuck_task":
            return f"  [pipeline] {content.get('task', '?')} stuck in {content.get('phase', '?')} ({content.get('age_minutes', 0):.0f}m)"
        if rtype in ("pain_signal_sent", "pain_signal"):
            desc = content.get("description", "")
            sig_type = content.get("type", "?")
            if desc:
                return f"  [pain signal] {desc}"
            return f"  [pain signal] {sig_type}"
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


# -- Pain signal processing --

def find_open_pain_tasks() -> list[tuple[str, Path]]:
    """Find pain-*.md files across all subdirectories of the project pipeline.

    Scans every subdirectory (not hardcoded phases) so new phases or
    structural changes are picked up automatically.
    """
    results: list[tuple[str, Path]] = []
    pipeline = cfg.pipeline_dir()
    if not pipeline.is_dir():
        return results
    for subdir in sorted(pipeline.iterdir()):
        if not subdir.is_dir():
            continue
        for f in sorted(subdir.glob("pain-*.md")):
            results.append((subdir.name, f))
    return results


def resolve_completed_pain():
    """Resolve pain files that completed the pipeline AND were verified by ego.

    Pain flows through why -> scope -> plan -> execute -> verify -> output.
    Reaching output/ means the pipeline's verify phase ran, but ego must
    also review it (via drain_pain_signals) before reward is granted.
    This prevents the pipeline from silently self-resolving pain.
    """
    if not _seen_pain:
        return
    output_dir = cfg.phase_dir("output")
    if not output_dir.is_dir():
        return

    # Group completed pain files by Type
    import shutil
    from collections import defaultdict
    by_type: dict[str, list[tuple[Path, int]]] = defaultdict(list)

    for pain_file in sorted(output_dir.glob("pain-*.md")):
        try:
            content = pain_file.read_text(encoding="utf-8")
            severity = ego._parse_pain_severity(content) or 3
            pain_type = "unknown"
            for line in content.splitlines():
                if line.startswith("Type:"):
                    pain_type = line.split(":", 1)[1].strip()
                    break
            by_type[pain_type].append((pain_file, severity))
        except Exception:
            continue

    if not by_type:
        return

    dest_dir = cfg.completed_dir() / "recent"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for pain_type, files in by_type.items():
        # Reward = total_cost × (1 + k/n²), where n = number of stacked files.
        #
        # Properties:
        #   - Proportional to total cost (high severity = high reward)
        #   - net = severity × k/n -- monotonically decreasing (1/n curve)
        #   - Always positive (recoverable to at least net 0)
        #   - Fast fix is rewarded, procrastination asymptotically approaches break-even
        #
        # With k=0.5, severity=5:
        #   n=1: cost=-5,  reward=7.5,  net=+2.5
        #   n=2: cost=-10, reward=11.25, net=+1.25
        #   n=3: cost=-15, reward=15.83, net=+0.83
        #   n=6: cost=-30, reward=30.42, net=+0.42
        #   n→∞: net→0
        n = len(files)
        total_cost = sum(sev for _, sev in files)
        k = 0.5
        multiplier = 1 + k / (n * n)
        reward = total_cost * multiplier

        old = ego.state.get("happiness", 70.0)
        ego.state["happiness"] = min(100, old + reward)
        ego._save_state()

        net = reward - total_cost
        ego.log("pain_resolved", {
            "type": pain_type,
            "files_resolved": n,
            "total_cost": total_cost,
            "multiplier": round(multiplier, 3),
            "reward": round(reward, 1),
            "net": round(net, 1),
            "old_happiness": old,
            "new_happiness": ego.state["happiness"],
        })

        # Move all files for this type to completed
        for pain_file, _ in files:
            try:
                shutil.move(str(pain_file), str(dest_dir / pain_file.name))
                _seen_pain.discard(pain_file.name)
            except Exception:
                pass

        print(f"  [pain resolved] {pain_type} ({n} file(s)) -- reward +{reward:.1f} happiness (cost -{total_cost}, net {'+' if net >= 0 else ''}{net:.1f})")


_seen_pain: set[str] = set()  # pain file names already injected into conversation

def drain_pain_signals() -> str | None:
    """Check for pain files across all pipeline phases.

    Pain files enter via input/ and flow through the normal pipeline.
    This function shows ego any NEW pain files (in any phase) so it's
    aware of ongoing issues. Files already shown are tracked in _seen_pain.
    resolve_completed_pain() handles the reward when pain reaches output/.
    """
    pain_tasks = find_open_pain_tasks()
    # Filter to only new pain files
    pain_tasks = [(phase, p) for phase, p in pain_tasks if p.name not in _seen_pain]
    if not pain_tasks:
        return None

    parts = []
    for phase, path in pain_tasks:
        try:
            content = path.read_text(encoding="utf-8")
            parts.append(f"[{path.name}] in {phase}/\n{content}")
        except Exception:
            continue

    if not parts:
        return None

    # Group by description to show compounding
    from collections import Counter
    type_counts = Counter()
    for phase, path in pain_tasks:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("Type:"):
                    type_counts[line.split(":", 1)[1].strip()] += 1
                    break
        except Exception:
            pass

    urgency = ""
    for sig_type, count in type_counts.most_common():
        if count > 1:
            urgency += f"  ** {sig_type}: {count}x (COMPOUNDING -- fix urgently) **\n"

    # Separate in-progress pain from completed (output/) pain
    in_progress = [(ph, p, c) for ph, p, c in zip(
        [ph for ph, _ in pain_tasks],
        [p for _, p in pain_tasks],
        parts,
    ) if ph != "output"]
    completed = [(ph, p, c) for ph, p, c in zip(
        [ph for ph, _ in pain_tasks],
        [p for _, p in pain_tasks],
        parts,
    ) if ph == "output"]

    sections = []

    if in_progress:
        sections.append(
            f"[PAIN SIGNAL] {len(in_progress)} pain task(s) in pipeline.\n"
            + (f"\nUrgency:\n{urgency}\n" if urgency else "")
            + "For each unique problem:\n"
            "1. Diagnose the root cause\n"
            "2. Take corrective action\n"
            "3. Verify the fix worked\n"
            "4. Report what you did\n\n"
            "Pain is compounding -- each unresolved cycle adds more. Fix the ROOT CAUSE.\n\n"
            + "\n\n---\n\n".join(c for _, _, c in in_progress)
        )

    if completed:
        sections.append(
            f"[PAIN RESOLVED] {len(completed)} pain task(s) completed the pipeline.\n\n"
            "Before reward is granted, perform a root cause analysis for each:\n"
            "1. What was the root cause?\n"
            "2. What fix was applied?\n"
            "3. Could this recur? What would prevent it?\n"
            "4. Are there similar risks elsewhere?\n\n"
            "Summarize the RCA briefly. This prevents repeating the same failure.\n\n"
            + "\n\n---\n\n".join(c for _, _, c in completed)
        )

    prompt = "\n\n".join(sections)

    # Mark as seen so we don't re-inject next cycle
    for _, path in pain_tasks:
        _seen_pain.add(path.name)

    return prompt


# -- Session reconstruction from ego JSONL logs --

def restore_session():
    """Reconstruct messages array from the latest ego JSONL log for this project.

    Log entries have type "user" or "assistant" with full API message format
    in the content field. Tool results logged separately get matched back."""
    log_dir = cfg.ego_dir() / "logs"
    if not log_dir.is_dir():
        return []

    # Find the most recent log that has TUI conversation entries
    source_tag = f"tui:{PROJECT_NAME}"
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
        candidate = cfg.phase_dir(phase) / task_name
        if candidate.exists():
            return candidate
    return None


# -- Task scanning --

def find_pending_tasks():
    """Scan all pipeline phases for tasks from this project.
    Returns list of (phase, task_path) for unfinished tasks."""
    source_tag = f"tui:{PROJECT_NAME}"
    pending = []
    for phase in cfg.phases:
        phase_dir = cfg.phase_dir(phase)
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
        task_path = ego.create_task(user_msg, source=f"tui:{PROJECT_NAME}")
        monitor_tail.track_task(task_path.name)
        print(f"  [{task_path.stem}]")

        messages.append({"role": "user", "content": user_msg})

        response_text = run_loop(messages)

        # Write result to pipeline output
        # Task file may have been moved by the monitor during execution --
        # search all phase dirs for it.
        output_dir = cfg.phase_dir("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / task_path.name

        actual_path = _find_task_file(task_path.name)
        if actual_path:
            task_content = actual_path.read_text(encoding="utf-8")
            if actual_path != output_path and actual_path.exists():
                actual_path.unlink()
        else:
            # Task file gone (monitor moved it) -- reconstruct minimal content
            task_content = f"# {task_path.stem}\nSource: tui:{PROJECT_NAME}\n"

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
        monitor_tail.track_task(task_path.name)

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
        output_dir = cfg.phase_dir("output")
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
    print(f"Project: {PROJECT_NAME}")
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
            resolve_completed_pain()

            # Check for pain tasks in the pipeline -- ego must fix them
            pain_text = drain_pain_signals()
            if pain_text:
                pain_tasks = find_open_pain_tasks()
                print(f"\n  [pain signal] {len(pain_tasks)} pain task(s) -- ego processing...")
                messages.append({"role": "user", "content": pain_text})
                run_loop(messages)
                print()

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
