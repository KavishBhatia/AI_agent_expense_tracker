#!/bin/bash
# Double-click this file in Finder to stop the Expense Tracker app.
cd "$(dirname "$0")"
PID_FILE="$(pwd)/.expense_tracker.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "Expense Tracker is not running (no PID file found)."
    exit 0
fi

read -r PID < "$PID_FILE" || PID=""
if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Expense Tracker stopped."
else
    echo "Process was not running."
fi
rm -f "$PID_FILE"
