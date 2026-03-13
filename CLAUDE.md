# Neural Pipeline

Brain-inspired agent pipeline. Tasks flow through phases (why -> scope -> plan -> execute -> verify) with manager and worker agents.

## TUI (primary interface)

The TUI (`tui.py`) is a thin shell around Ego. Run it from any project directory with `cct`.

```
cct                          # Interactive mode
cct "add dark mode"          # One-shot
```

### How it works

1. Every user message -> `ego.create_task()` -> task file in `pipeline/input/`
2. API calls go through `ego.send_message()` -> logged to `ego/logs/` JSONL
3. Tools execute against CWD (user's project, not pipeline root)
4. Results written to `pipeline/output/task-NNNN.md`

### Session persistence

No separate session files. Two existing sources of truth:

- **Task files** (`pipeline/{phase}/task-NNNN.md`) -- what was requested, where it is, what happened
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
User -> TUI (tui.py) -> Ego -> API -> tools against CWD -> pipeline/output/
                         |
                         v
                    ego/logs/ (JSONL -- full API message format)
                    pipeline/input/ (task files)
                    pipeline/output/ (completed task files)
```

## Key Files

| File | Purpose |
|------|---------|
| `tui.py` | TUI entry point -- I/O shell around Ego |
| `src/ego.py` | Task creation, status, review, happiness, JSONL logging |
| `src/agent_base.py` | SDK client, send_message(), message sanitization, max_tokens resolution |
| `src/tools.py` | Tool definitions + path safety (allowed_roots) |
| `src/config.py` | Reads system/config.yaml |
| `src/credentials.py` | Retrieves API key from OS credential store |
| `src/monitor.py` | Daemon, watches pipeline dirs, spawns managers |
| `system/config.yaml` | Models, phases, thresholds |

## Design Principles

- **Attention model**: The TUI checks for pipeline activity (monitor log) between loop iterations, not during. Like the brain: the autonomic nervous system fires constantly, but conscious attention only processes those signals in the gaps between active thought. No background threads -- just check between steps.
- **Pain mode = hypervigilance**: When happiness drops below the improvement threshold (chronic pain), a background thread enables real-time monitor log tailing -- like how chronic pain forces conscious attention to signals normally filtered out. Normal mode: check between steps. Improvement mode: live stream.

## Windows Notes

- Subprocesses (managers, workers) use `subprocess.CREATE_NO_WINDOW` to prevent new console windows from opening on every spawn. Applied in `monitor.py` and `manager_base.py`.
- Session restore sanitizes restored messages to drop orphaned `tool_result` blocks that reference missing `tool_use` ids (can happen after interrupted sessions).

## API

- Endpoint: TrendMicro proxy (api.rdsec.trendmicro.com)
- Credential: NEURAL_PIPELINE/API_KEY in OS credential store
- Models: claude-sonnet-4-6 (ego/manager), claude-haiku-4-5 (worker/monitor)
