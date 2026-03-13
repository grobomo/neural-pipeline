# Neural Pipeline

Brain-inspired agent pipeline. Tasks flow through phases (why -> scope -> plan -> execute -> verify) with manager and worker agents.

## TUI (primary interface)

The TUI (`tui.py`) is a thin shell around Ego. Run it from any project directory with `cct`.

```
cct                          # Interactive mode
cct "add dark mode"          # One-shot
```

### How it works

1. Every user message -> `ego.create_task()` -> task file in project's `input/`
2. API calls go through `ego.send_message()` -> logged to `ego/logs/` JSONL
3. Tools execute against CWD (user's project, not pipeline root)
4. Results written to project's `output/task-NNNN.md`

### Session persistence

No separate session files. Two existing sources of truth:

- **Task files** (`pipeline/projects/{slug}/{phase}/task-NNNN.md`) -- what was requested, where it is, what happened
- **Ego JSONL logs** (`ego/logs/*-ego.jsonl`) -- full API messages (user, assistant, tool calls, tool results)

On startup the TUI:
1. Reconstructs conversation from the latest ego JSONL log (entries tagged `tui:{project}`)
2. Scans all pipeline phases for unfinished tasks from this project
3. Resumes unfinished tasks automatically (unless interrupted)
4. Loads completed tasks as context so Claude knows what was already done

### Commands

| Input | Action |
|-------|--------|
| (any text) | Creates task, runs agentic loop, writes result to output/ |
| `status` | Shows pipeline state (tasks in each phase, happiness, notifications) |
| `new` | Clears in-memory session (logs remain on disk) |
| `quit`/`exit`/`q` | Exit |

### Environment Variables

| Var | Effect |
|-----|--------|
| `CCT_DEBUG=1` | Forces live monitor log tailing (pain mode) regardless of happiness level |

## Architecture

```
User -> TUI (tui.py) -> Ego -> API -> tools against CWD
                         |
                         v
                    ego/logs/ (JSONL -- full API message format)
                    pipeline/projects/{slug}/input/   (task files per project)
                    pipeline/projects/{slug}/output/  (completed tasks per project)
                    pipeline/projects/{slug}/{phase}/  (why/scope/plan/execute/verify)
```

### Per-project isolation

Each target project gets its own pipeline folder under `pipeline/projects/`. The slug is `{dirname}-{hash6}` where hash6 is the first 6 chars of SHA-256 of the absolute path. This prevents collisions when two projects share the same directory name.

```
pipeline/projects/
  my-app-a1b2c3/        # /home/user/code/my-app
    input/
    why/
    scope/
    ...
    output/
  my-app-f4e5d6/        # /other/path/my-app (different hash)
    input/
    ...
```

The monitor watches `pipeline/projects/` for new project directories and sets up phase watchers automatically. Config methods: `set_project(path)`, `set_project_slug(slug)`, `pipeline_dir()`, `phase_dir(phase)`, `all_project_dirs()`.

## Key Files

| File | Purpose |
|------|---------|
| `tui.py` | TUI entry point -- I/O shell around Ego |
| `src/ego.py` | Task creation, status, review, happiness, JSONL logging |
| `src/agent_base.py` | SDK client, send_message(), message sanitization, max_tokens resolution |
| `src/tools.py` | Tool definitions + path safety (allowed_roots) |
| `src/config.py` | Reads system/config.yaml, per-project pipeline routing |
| `src/credentials.py` | Retrieves API key from OS credential store |
| `src/monitor.py` | Daemon, watches all project dirs, spawns managers |
| `system/config.yaml` | Models, phases, thresholds |

## Design Principles

- **Attention model**: The TUI checks for pipeline activity (monitor log + task file changes) between loop iterations, not during. Like the brain: the autonomic nervous system fires constantly, but conscious attention only processes those signals in the gaps between active thought. No background threads -- just check between steps.
- **Pain mode = hypervigilance**: When happiness drops below the improvement threshold (chronic pain), a background thread enables real-time monitoring -- like how chronic pain forces conscious attention to signals normally filtered out. Normal mode: check between steps. Improvement mode: live stream.
- **Task file as single source of truth**: Each phase manager appends a `## Phase` section to the task file as it processes. The TUI watches tracked task files for growth and displays new sections inline -- no separate event logs or notification files needed.

## Windows Notes

- Subprocesses (managers, workers) use `subprocess.CREATE_NO_WINDOW` to prevent new console windows from opening on every spawn. Applied in `monitor.py` and `manager_base.py`.
- Session restore sanitizes restored messages to drop orphaned `tool_result` blocks that reference missing `tool_use` ids (can happen after interrupted sessions).

## API

- Endpoint: TrendMicro proxy (api.rdsec.trendmicro.com)
- Credential: NEURAL_PIPELINE/API_KEY in OS credential store
- Models: claude-sonnet-4-6 (ego/manager), claude-haiku-4-5 (worker/monitor)
