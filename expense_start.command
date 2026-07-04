#!/bin/bash
# Double-click this file in Finder to start the Expense Tracker app.
set -e
cd "$(dirname "$0")"
PID_FILE="$(pwd)/.expense_tracker.pid"
LOG_FILE="/tmp/expense_tracker.log"

if [ -f "$PID_FILE" ]; then
    read -r PID < "$PID_FILE" || PID=""
    if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
        echo "Expense Tracker is already running."
        open http://127.0.0.1:8050
        exit 0
    fi
    rm -f "$PID_FILE"
fi

echo "Starting Expense Tracker..."
.venv/bin/python app.py > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 3
open http://127.0.0.1:8050
echo "Expense Tracker started. Close this window to keep it running in the background."
