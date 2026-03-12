#!/usr/bin/env bash
# Neural Pipeline -- Start the monitor daemon
# Usage: ./1_start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.tmp/monitor.pid"
LOG_DIR="$SCRIPT_DIR/monitor/logs"

mkdir -p "$SCRIPT_DIR/.tmp" "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Monitor already running (PID $PID)"
        exit 0
    else
        echo "Stale PID file found, cleaning up"
        rm -f "$PID_FILE"
    fi
fi

# Install dependencies if needed
if ! python -c "import anthropic, watchdog, yaml, keyring" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
fi

# Validate credentials
if ! python -c "
import sys, os
sys.path.insert(0, '$SCRIPT_DIR/src')
sys.path.insert(0, '$SCRIPT_DIR')
from src.credentials import get_api_key
try:
    key = get_api_key()
    print('Credential check: OK')
except Exception as e:
    print(f'Credential check FAILED: {e}')
    sys.exit(1)
" 2>&1; then
    echo "Cannot start -- credential retrieval failed."
    echo "Store the API key: python ~/.claude/skills/credential-manager/store_gui.py NEURAL_PIPELINE/API_KEY"
    exit 1
fi

# Start monitor daemon
echo "Starting Neural Pipeline monitor..."
nohup python -m src.monitor "$SCRIPT_DIR" > "$LOG_DIR/monitor-stdout.log" 2>&1 &
MONITOR_PID=$!
echo "$MONITOR_PID" > "$PID_FILE"
echo "Monitor started (PID $MONITOR_PID)"
echo "Logs: $LOG_DIR/"
