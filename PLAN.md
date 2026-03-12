# Neural Pipeline -- Integration Plan

## Status: Option B (translator) merged to main, pushed to grobomo/neural-pipeline

## Completed
- [x] Git repo created, pushed to grobomo/neural-pipeline
- [x] Three option branches created (a-dumb-pipe, b-translator, c-ego-is-session)
- [x] Option B merged to main
- [x] Guard hook tested -- blocks code edits in any project, allows meta-files
- [x] Ego CLI tested -- creates tasks in pipeline/input/
- [x] SessionStart autostart hook created (hooks/neural-pipeline-autostart.js)
- [x] install.sh updated to include SessionStart hook
- [x] settings.local.json regenerated with SessionStart hook
- [x] monitor.py bug fixed -- scan_for_existing_tasks() now scans input/ too
- [x] Autostart hook rewritten as pure Node.js (no bash/shell spawns, windowsHide)

## TODO (next session)
- [ ] E2E test: new session in this project, verify autostart fires, monitor starts silently
- [ ] E2E test: create task via ego, monitor picks it up, routes through all phases
- [ ] E2E test: cat gif background request on todo-app end-to-end
- [ ] Commit fixes and push to grobomo/neural-pipeline

## Known Bugs Fixed
1. monitor.py scan_for_existing_tasks() didn't scan input/ -- FIXED (now scans input/ on startup)
2. Daemon spawn opened visible cmd windows on Windows -- FIXED (pure Node spawn, windowsHide, shell:false)
3. Watchdog race: task created before monitor starts -- FIXED (input/ scan on startup)

## Uncommitted Changes
- src/monitor.py -- scan_for_existing_tasks() now includes input/
- hooks/neural-pipeline-autostart.js -- rewritten as pure Node.js, no shell spawns
- install.sh -- added SessionStart hook to installer
- .claude/settings.local.json -- includes SessionStart autostart hook
- PLAN.md -- this file

## Architecture (Option B -- Translator)
```
Session starts -> autostart hook -> monitor daemon (silent, background)
User speaks -> Claude translates intent -> python -m src.ego "request with context" -> task in input/
Monitor -> routes task through: why -> scope -> plan -> execute -> verify -> output/
Claude -> reads output/ -> presents results with summary to user
```

## Key Files
- hooks/neural-pipeline-autostart.js -- SessionStart, auto-starts monitor (pure Node, no shell)
- hooks/neural-pipeline-guard.js -- PreToolUse, blocks direct code edits
- hooks/neural-pipeline-notifications.js -- UserPromptSubmit, injects notifications
- hooks/neural-pipeline-heartbeat.js -- UserPromptSubmit, warns if monitor down
- src/monitor.py -- daemon, watches pipeline dirs + input/, spawns managers
- src/ego.py -- CLI interface, creates tasks, reviews output
- src/worker_base.py -- worker agent, executes steps with tool sandbox
- src/tools.py -- tool definitions + path safety (allowed_roots)
- install.sh -- writes .claude/settings.local.json with all hooks
- 1_start.sh -- manual monitor start (autostart hook replaces this for Claude sessions)
