#!/usr/bin/env bash
# Neural Pipeline -- Stop the monitor daemon
# Usage: ./3_stop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.tmp/monitor.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "Monitor is not running (no PID file)"
    exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping monitor (PID $PID)..."
    kill "$PID"
    # Wait up to 10 seconds for graceful shutdown
    for i in $(seq 1 10); do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    if kill -0 "$PID" 2>/dev/null; then
        echo "Force killing monitor..."
        kill -9 "$PID" 2>/dev/null || true
    fi
    echo "Monitor stopped"
else
    echo "Monitor was not running (stale PID)"
fi

rm -f "$PID_FILE"
