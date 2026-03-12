#!/usr/bin/env bash
# Neural Pipeline -- Install project hooks into Claude Code
# Creates .claude/settings.local.json with project-specific hooks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/hooks"
SETTINGS_DIR="$SCRIPT_DIR/.claude"
SETTINGS_FILE="$SETTINGS_DIR/settings.local.json"

echo "=== Neural Pipeline Hook Installer ==="
echo ""

# Verify hooks exist
for hook in neural-pipeline-guard.js neural-pipeline-notifications.js neural-pipeline-heartbeat.js; do
  if [ ! -f "$HOOKS_DIR/$hook" ]; then
    echo "ERROR: Missing hook: $HOOKS_DIR/$hook"
    exit 1
  fi
done
echo "[OK] All hook files found"

# Create .claude directory
mkdir -p "$SETTINGS_DIR"

# Write project-local settings
cat > "$SETTINGS_FILE" << 'SETTINGS'
{
  "hooks": {
    "PreToolUse": [
      {
        "type": "command",
        "command": "node hooks/neural-pipeline-guard.js",
        "matcher": "Edit|Write|Bash"
      }
    ],
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "node hooks/neural-pipeline-notifications.js"
      },
      {
        "type": "command",
        "command": "node hooks/neural-pipeline-heartbeat.js"
      }
    ]
  }
}
SETTINGS

echo "[OK] Project hooks written to $SETTINGS_FILE"
echo ""
echo "Hooks installed:"
echo "  PreToolUse:        neural-pipeline-guard.js (BLOCKING -- forces ego routing)"
echo "  UserPromptSubmit:  neural-pipeline-notifications.js (injects ego notifications)"
echo "  UserPromptSubmit:  neural-pipeline-heartbeat.js (warns if monitor is down)"
echo ""
echo "To test: open Claude Code in this directory and try to edit a .py file."
echo "The guard hook should block it and tell you to use the ego."
echo ""
echo "To start the pipeline: ./1_start.sh"
echo "To submit work: python -m src.ego 'your request'"
