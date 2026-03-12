# Neural Pipeline

Brain-inspired agent pipeline. Tasks flow through phases (why -> scope -> plan -> execute -> verify) with manager and worker agents.

## Core Rule: Dumb Pipe -- Verbatim Relay to Ego

**DO NOT write code, create files, or do project work directly.** When the guard blocks an edit,
relay the user's exact words to ego -- verbatim, no rephrasing, no interpretation, no enhancement:

```bash
python -m src.ego "the user's exact words"   # Relay verbatim
python -m src.ego "status"                   # Check pipeline
python -m src.ego "review task N"            # Review result
python -m src.ego "approve task N"           # Accept
python -m src.ego "reject task N -- reason"  # Reject
```

**Verbatim relay means:**
- Copy the user's words exactly as typed
- Do NOT rephrase, enhance, or interpret the request
- Do NOT add context, clarification, or your own words
- Show raw ego output without commentary

The hooks enforce this -- `neural-pipeline-guard.js` blocks Edit/Write on project files.

## What You CAN Do Directly

- Read any file (for context, to answer questions)
- Edit hooks/, system/, tests/, config files, CLAUDE.md, SPEC.md, BUILD_PLAN.md
- Run ego commands, tests, lifecycle scripts
- Git operations

## Architecture

```
User -> Claude Code -> ego -> pipeline -> results -> ego -> Claude Code -> User
```

The pipeline is transparent. User says "write a function", Claude calls ego verbatim, ego creates task, pipeline processes it, ego presents results. Claude shows raw output only.

## Hooks (project-local)

| Hook | Event | Purpose |
|------|-------|---------|
| neural-pipeline-guard.js | PreToolUse | BLOCKS direct work -- forces ego routing |
| neural-pipeline-notifications.js | UserPromptSubmit | Injects ego notifications into context |
| neural-pipeline-heartbeat.js | UserPromptSubmit | Warns if monitor daemon is stopped |

## API

- Endpoint: TrendMicro proxy (api.rdsec.trendmicro.com)
- Credential: NEURAL_PIPELINE/API_KEY in OS credential store
- Models: claude-sonnet-4-6 (ego/manager), claude-haiku-4-5 (worker/monitor)
