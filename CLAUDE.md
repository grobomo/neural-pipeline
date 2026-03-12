# Neural Pipeline

Brain-inspired agent pipeline. Tasks flow through phases (why -> scope -> plan -> execute -> verify) with manager and worker agents.

## Core Rule: Claude IS the Ego

**DO NOT write code, create files, or do project work directly.** Instead, create task files in `pipeline/input/` and let the pipeline process them.

Claude acts as the ego directly -- no CLI wrapper needed. The workflow:

1. Read `system/next-task-id`, increment it, write back
2. Create `pipeline/input/task-NNNN.md` with this format:
   ```markdown
   # Task NNNN: Short description
   Created: <ISO timestamp>
   Source: user
   Status: pending

   ## User Request
   <the user's request with full context>

   ## References
   - C:/path/to/project/directory
   - Any relevant file paths
   ```
3. Poll `pipeline/output/` for the completed task file
4. Read the output, present results to the user
5. Based on user feedback:
   - Approve: move task to `completed/recent/`
   - Reject: append rejection reason, move to `failed/recent/`

## What You CAN Do Directly

- Read any file (for context, to answer questions)
- Write task files to pipeline/input/
- Read/move files in pipeline/output/, completed/, failed/
- Read/write system/next-task-id
- Edit hooks/, system/, tests/, config files, CLAUDE.md, SPEC.md, BUILD_PLAN.md
- Git operations

## Architecture

```
User -> Claude Code -> [write task file] -> pipeline/input/ -> pipeline -> pipeline/output/ -> Claude Code -> User
```

Claude writes task files directly. No ego CLI. The pipeline monitor picks up tasks from input/, routes through phases, deposits results in output/. Claude reads output and presents to user.

## Hooks (project-local)

| Hook | Event | Purpose |
|------|-------|---------|
| neural-pipeline-guard.js | PreToolUse | BLOCKS direct code work -- forces task file creation |
| neural-pipeline-notifications.js | UserPromptSubmit | Injects ego notifications into context |
| neural-pipeline-heartbeat.js | UserPromptSubmit | Warns if monitor daemon is stopped |

## API

- Endpoint: TrendMicro proxy (api.rdsec.trendmicro.com)
- Credential: NEURAL_PIPELINE/API_KEY in OS credential store
- Models: claude-sonnet-4-6 (ego/manager), claude-haiku-4-5 (worker/monitor)
