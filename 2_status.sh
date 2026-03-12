#!/usr/bin/env bash
# Neural Pipeline -- Show system status
# Usage: ./2_status.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.tmp/monitor.pid"

echo "=== Neural Pipeline Status ==="
echo ""

# Monitor status
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Monitor: RUNNING (PID $PID)"
    else
        echo "Monitor: DEAD (stale PID $PID)"
    fi
else
    echo "Monitor: STOPPED"
fi
echo ""

# Heartbeat
HEARTBEAT="$SCRIPT_DIR/monitor/health/heartbeat"
if [ -f "$HEARTBEAT" ]; then
    echo "Last heartbeat: $(cat "$HEARTBEAT")"
else
    echo "Last heartbeat: never"
fi
echo ""

# Task counts per phase
echo "--- Pipeline ---"
for phase in input why scope plan execute verify output; do
    dir="$SCRIPT_DIR/pipeline/$phase"
    if [ -d "$dir" ]; then
        count=$(find "$dir" -maxdepth 1 -name "task-*.md" 2>/dev/null | wc -l)
        printf "  %-10s %d tasks\n" "$phase:" "$count"
    fi
done
echo ""

echo "--- Post-Pipeline ---"
for folder in completed/recent completed/archive failed/recent failed/archive paused blocked; do
    dir="$SCRIPT_DIR/$folder"
    if [ -d "$dir" ]; then
        count=$(find "$dir" -maxdepth 1 -name "task-*.md" 2>/dev/null | wc -l)
        printf "  %-25s %d tasks\n" "$folder:" "$count"
    fi
done
echo ""

# Ego happiness
STATE="$SCRIPT_DIR/ego/state.yaml"
if [ -f "$STATE" ]; then
    happiness=$(python -c "
import yaml
with open('$STATE') as f:
    d = yaml.safe_load(f)
print(f\"Happiness: {d.get('happiness', '?')}/100\")
print(f\"Tasks completed: {d.get('tasks_completed', 0)}\")
print(f\"Tasks failed: {d.get('tasks_failed', 0)}\")
" 2>/dev/null || echo "Could not read ego state")
    echo "--- Ego ---"
    echo "  $happiness"
fi
echo ""

# Pending notifications
NOTIF_DIR="$SCRIPT_DIR/ego/notifications"
if [ -d "$NOTIF_DIR" ]; then
    notif_count=$(find "$NOTIF_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l)
    echo "Pending notifications: $notif_count"
fi
