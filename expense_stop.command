#!/bin/bash
# Double-click this file in Finder to stop the Expense Tracker app.
PID_FILE="/tmp/expense_tracker.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "Expense Tracker is not running (no PID file found)."
    exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Expense Tracker stopped."
else
    echo "Process was not running."
fi
rm -f "$PID_FILE"
