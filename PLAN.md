# Neural Pipeline -- Integration Plan

## Status: TUI complete, session persistence via ego JSONL logs

## Completed
- [x] Git repo created, pushed to grobomo/neural-pipeline
- [x] Option B (translator) merged to main
- [x] Guard hook blocks direct code edits, forces ego routing
- [x] SessionStart autostart hook (pure Node.js, no shell spawns)
- [x] monitor.py scans input/ on startup (crash recovery)
- [x] TUI created -- thin shell around Ego
- [x] Every message creates a task in pipeline/input/
- [x] API calls go through ego.send_message() with full message logging
- [x] Tools execute against CWD, not pipeline root
- [x] Results written to pipeline/output/
- [x] Session restore from ego JSONL logs (no separate session files)
- [x] Pending task scan + auto-resume on startup
- [x] Completed tasks loaded as context
- [x] PowerShell `cct` function in $profile
- [x] agent_base.send_message() logs full API message format for reconstruction
- [x] CLAUDE.md updated with TUI docs

## TODO
- [ ] E2E test: cct from todo-app dir, full round trip
- [ ] Commit and push to grobomo/neural-pipeline
