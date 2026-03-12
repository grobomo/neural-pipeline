# Neural Pipeline -- Build Plan

Created: 2026-03-12
Updated: 2026-03-12 (E2E test passed)
Credential: NEURAL_PIPELINE/API_KEY (stored in OS credential store)
API Endpoint: https://api.rdsec.trendmicro.com/prod/aiendpoint/ (TrendMicro proxy)
Models: claude-sonnet-4-6 (ego/manager), claude-haiku-4-5 (worker/monitor)

## Phase 1: Foundation [COMPLETE]
**Goal:** Skeleton that runs -- folders exist, config loads, credentials work, SDK makes a call.

Delivered:
- All 50+ spec folders created
- system/config.yaml with all settings including custom API endpoint
- requirements.txt (anthropic, watchdog, pyyaml, keyring)
- src/credentials.py -- cross-platform credential retrieval
- src/config.py -- typed config access with path helpers
- 1_start.sh, 2_status.sh, 3_stop.sh lifecycle scripts
- SDK call verified through TrendMicro proxy

## Phase 2: Template Agent [COMPLETE]
**Goal:** Base classes that all agents inherit.

Delivered:
- src/agent_base.py -- SDK wrapper, JSONL logging, agentic tool-use loop
- src/manager_base.py -- step creation, prediction, worker spawning, review, scoring
- src/worker_base.py -- step execution, output writing, file movement
- src/ego.py -- CLI, task creation, status, approve/reject, happiness, notifications
- src/monitor.py -- watchdog events, manager spawning, health checks, heartbeat
- src/tools.py -- 6 tool schemas + sandboxed execution (read, write, edit, shell, search, list)
- src/rules.py -- YAML frontmatter parsing, keyword matching, score updates
- src/worker_runner.py, src/manager_runner.py -- subprocess entry points
- 9 unit tests passing

## Phase 3: Monitor Daemon [COMPLETE]
**Goal:** Watchdog-based daemon that detects file events and spawns managers.

Delivered:
- Watchdog event handler for all phase folders + input/
- Input-to-why routing (monitor moves task from input/ to why/)
- Manager subprocess spawning via Popen
- Health check loop (stuck task detection, heartbeat file)
- Pain signal writing to ego/pain-signals/
- Crash recovery scan on startup

## Phase 4: Ego Agent [COMPLETE]
**Goal:** CLI-invocable ego that creates tasks, reviews results, manages happiness.

Delivered:
- `python -m src.ego "request"` -- creates task
- `python -m src.ego "status"` -- reports pipeline state
- `python -m src.ego "review task N"` -- reviews output
- `python -m src.ego "approve task N"` -- moves to completed, happiness up
- `python -m src.ego "reject task N -- reason"` -- moves to failed, happiness down
- Investigation delegation (write to ego/investigations/)
- Notification writing (ego/notifications/)
- Happiness mechanics (signals, decay, improvement mode)

## Phase 5: Phase Agents [COMPLETE]
**Goal:** Working manager + worker for each pipeline phase.

Delivered:
- reference.md for each phase (why, scope, plan, execute, verify)
- ego/reference.md and monitor/reference.md
- system/agents/ prompts: manager-base.md, worker-base.md, ego.md, monitor.md
- pipeline/pipeline-reference.md (global reference)
- system/cron/reflection.yaml, sleep.yaml (job definitions)
- All 5 phases use ManagerBase/WorkerBase generics with phase-specific reference.md
- Prediction error scoring working (exceeded/met/fell-short)

## Phase 6: Claude Code Integration [COMPLETE]
**Goal:** Skill + hook so user can interact via Claude Code.

Delivered:
- SKILL.md at project root
- hooks/notification-check.js (UserPromptSubmit -- injects ego notifications)
- hooks/heartbeat-check.js (UserPromptSubmit -- warns if monitor is dead)
- All paths use pathlib -- no hardcoded platform-specific paths

## Phase 7: E2E Test [COMPLETE]
**Goal:** Full pipeline test with real SDK calls.

Delivered:
- tests/test_pipeline.py -- 9 unit tests, all passing
- tests/test_e2e.py -- full pipeline E2E with live SDK calls
- E2E result: task flowed input -> why -> scope -> plan -> execute -> verify -> output -> completed
- Scoring: why=+1, scope=+3(exceeded), plan=+1, execute=+1, verify=-2(fell-short)
- Happiness: 70 -> 85 after approval
- Artifacts: 11 steps, 13 worker logs, 13 manager logs, 11 predictions
- Pipeline created prime.py with docstring, type hints, edge cases, sqrt efficiency
- PDF report: not generated (deferred -- not critical for functionality)

## Bugs Fixed During E2E
1. self.config not set before _load_reference() in manager_base and worker_base (init order)
2. Worker output extraction: LLM response headers clashed with step file structure
3. Worker output too short when using tools: improved extraction + system prompt
4. Model names: TrendMicro proxy uses claude-haiku-4-5 not claude-haiku-4-5-20251001

## Key Decisions
- Credential key: NEURAL_PIPELINE/API_KEY
- API endpoint: TrendMicro proxy (api.rdsec.trendmicro.com)
- Code uses pathlib exclusively -- no hardcoded paths, cross-platform
- All agents use generic ManagerBase/WorkerBase -- phase-specific behavior via reference.md
- Monitor: watchdog library for filesystem events (no polling)
- No framework, no orchestrator, no swarm
- All agents log to individual JSONL files with datetime stamps
