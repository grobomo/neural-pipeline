"""Tool definitions and execution for Neural Pipeline workers.

Defines JSON schemas for tools that workers can call during execution.
Execute functions handle the actual operations (filesystem, shell, search).

Path safety: workers can operate on the pipeline root AND any project
directory listed in the task's ## References section. The allowed_roots
list is passed to execute_tool by the worker runner.
"""
import os
import subprocess
import glob as globlib
from pathlib import Path
from typing import Any


# -- Tool Schemas (Claude API format) --

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns the file text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to project root or absolute).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-based). Optional.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read. Optional.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories if needed. Overwrites existing content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to project root or absolute).",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace an exact string in a file with new content. The old_string must appear exactly once unless replace_all is true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace.",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default false).",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "shell",
        "description": "Execute a shell command and return stdout+stderr. Timeout: 120s.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command. Optional (defaults to project root).",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_files",
        "description": "Search file contents with regex. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (relative to project root). Optional.",
                },
                "include": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py'). Optional.",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_files",
        "description": "List files matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py', 'src/*.js').",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory for the glob. Optional (defaults to project root).",
                },
            },
            "required": ["pattern"],
        },
    },
]


# -- Path Safety --

# Additional allowed roots (set by worker/manager when task has external References)
_allowed_roots: list[Path] = []


def set_allowed_roots(roots: list[Path]):
    """Set additional allowed root directories (from task References)."""
    global _allowed_roots
    _allowed_roots = [Path(r).resolve() for r in roots]


def _resolve_path(path_str: str, project_root: Path) -> Path:
    """Resolve a path, ensuring it stays within allowed roots.

    Allowed roots = [project_root] + any directories from task References.
    This lets workers operate on external project directories.
    """
    p = Path(path_str)
    if not p.is_absolute():
        p = project_root / p
    p = p.resolve()

    # Check against all allowed roots
    all_roots = [project_root.resolve()] + _allowed_roots
    for root in all_roots:
        if str(p).startswith(str(root)):
            return p

    raise PermissionError(
        f"Path not in any allowed root: {path_str}\n"
        f"Allowed: {[str(r) for r in all_roots]}"
    )


# -- Tool Execution --

def execute_tool(tool_name: str, tool_input: dict, project_root: Path) -> str:
    """Execute a tool call and return the result as a string."""
    handlers = {
        "read_file": _exec_read_file,
        "write_file": _exec_write_file,
        "edit_file": _exec_edit_file,
        "shell": _exec_shell,
        "search_files": _exec_search_files,
        "list_files": _exec_list_files,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return f"Unknown tool: {tool_name}"
    try:
        return handler(tool_input, project_root)
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"


def _exec_read_file(inp: dict, root: Path) -> str:
    p = _resolve_path(inp["path"], root)
    if not p.exists():
        return f"File not found: {inp['path']}"
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    offset = inp.get("offset", 1) - 1
    limit = inp.get("limit", len(lines))
    selected = lines[max(0, offset):offset + limit]
    return "".join(selected)


def _exec_write_file(inp: dict, root: Path) -> str:
    p = _resolve_path(inp["path"], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(inp["content"], encoding="utf-8")
    return f"Wrote {len(inp['content'])} bytes to {inp['path']}"


def _exec_edit_file(inp: dict, root: Path) -> str:
    p = _resolve_path(inp["path"], root)
    if not p.exists():
        return f"File not found: {inp['path']}"
    text = p.read_text(encoding="utf-8")
    old = inp["old_string"]
    new = inp["new_string"]
    replace_all = inp.get("replace_all", False)

    count = text.count(old)
    if count == 0:
        return f"old_string not found in {inp['path']}"
    if count > 1 and not replace_all:
        return f"old_string found {count} times -- set replace_all=true or provide more context"

    if replace_all:
        text = text.replace(old, new)
    else:
        text = text.replace(old, new, 1)

    p.write_text(text, encoding="utf-8")
    replaced = count if replace_all else 1
    return f"Replaced {replaced} occurrence(s) in {inp['path']}"


# Active shell process -- set by _exec_shell, read by kill_active_shell()
_active_shell_proc: subprocess.Popen | None = None


def kill_active_shell() -> bool:
    """Kill the currently running shell subprocess, if any.

    Returns True if a process was killed, False if nothing was running.
    Called by TUI's SIGINT handler to interrupt commands without exiting.
    """
    global _active_shell_proc
    proc = _active_shell_proc
    if proc is None:
        return False
    try:
        proc.kill()
        return True
    except Exception:
        return False


def _exec_shell(inp: dict, root: Path) -> str:
    global _active_shell_proc
    cwd = root
    if "cwd" in inp:
        cwd = _resolve_path(inp["cwd"], root)
    try:
        kwargs = {
            "shell": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": str(cwd),
            "env": {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(inp["command"], **kwargs)
        _active_shell_proc = proc
        try:
            stdout, stderr = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return "Command timed out after 120 seconds"
        finally:
            _active_shell_proc = None

        output = stdout or ""
        if stderr:
            output += "\n--- stderr ---\n" + stderr
        if proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"
        return output[:50000]  # cap output size
    except Exception as e:
        _active_shell_proc = None
        if "killed" in str(e).lower() or isinstance(e, OSError):
            return "[command interrupted]"
        return f"Shell error: {e}"


def _exec_search_files(inp: dict, root: Path) -> str:
    import re
    search_path = root
    if "path" in inp:
        search_path = _resolve_path(inp["path"], root)

    pattern = re.compile(inp["pattern"])
    include = inp.get("include", "**/*")
    matches = []

    if search_path.is_file():
        files = [search_path]
    else:
        files = list(search_path.glob(include))

    for f in files[:500]:  # cap file count
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.search(line):
                    rel = f.relative_to(root) if str(f).startswith(str(root)) else f
                    matches.append(f"{rel}:{i}: {line}")
                    if len(matches) >= 200:
                        break
        except Exception:
            continue
        if len(matches) >= 200:
            break

    if not matches:
        return "No matches found"
    return "\n".join(matches)


def _exec_list_files(inp: dict, root: Path) -> str:
    base = root
    if "path" in inp:
        base = _resolve_path(inp["path"], root)
    results = sorted(base.glob(inp["pattern"]))[:500]
    if not results:
        return "No files matched"
    lines = []
    for r in results:
        try:
            rel = r.relative_to(root)
        except ValueError:
            rel = r
        lines.append(str(rel))
    return "\n".join(lines)
