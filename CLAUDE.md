# Neural Pipeline

Brain-inspired agent pipeline. Tasks flow through phases (why -> scope -> plan -> execute -> verify) with manager and worker agents.

## Core Rule: Translate Intent Into Clear Ego Commands

**Claude is a translator between user and ego.** Do NOT write code or do project work directly. Instead:

1. **Understand the user's intent** -- what are they actually trying to accomplish?
2. **Add relevant context** -- which project, which files are involved, what constraints apply
3. **Formulate a clear ego command** -- include a `## References` section with file paths
4. **Present results with commentary** -- summarize what happened and highlight key outcomes
5. **Ask clarifying questions** if intent is ambiguous before routing to ego

```bash
python -m src.ego "your request here"    # Create task
python -m src.ego "status"               # Check pipeline
python -m src.ego "review task N"        # Review result
python -m src.ego "approve task N"       # Accept
python -m src.ego "reject task N -- reason"  # Reject
```

Example of a well-translated ego command:
```bash
python -m src.ego "Add input validation to the login form

## References
- Project: /c/Users/joelg/Documents/ProjectsCL1/myapp
- File: src/components/LoginForm.tsx
- File: src/utils/validators.ts
- Context: Form currently has no client-side validation; add email format + password length checks"
```

The hooks enforce ego routing -- `neural-pipeline-guard.js` blocks Edit/Write on project files.

## What You CAN Do Directly

- Read any file (for context, to answer questions)
- Edit hooks/, system/, tests/, config files, CLAUDE.md, SPEC.md, BUILD_PLAN.md
- Run ego commands, tests, lifecycle scripts
- Git operations

## Architecture

```
User -> Claude Code -> ego -> pipeline -> results -> ego -> Claude Code -> User
```

The pipeline is transparent. User says "write a function", Claude understands intent, adds context, calls ego with a clear command. Ego creates task, pipeline processes it, ego presents results. Claude summarizes key outcomes for the user.

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
