#!/bin/bash
# Double-click this file in Finder to start the Expense Tracker app.
set -e
cd "$(dirname "$0")"

if [ -f /tmp/expense_tracker.pid ] && kill -0 "$(cat /tmp/expense_tracker.pid)" 2>/dev/null; then
    echo "Expense Tracker is already running."
    open http://127.0.0.1:8050
    exit 0
fi

echo "Starting Expense Tracker..."
.venv/bin/python app.py > /tmp/expense_tracker.log 2>&1 &
echo $! > /tmp/expense_tracker.pid
sleep 3
open http://127.0.0.1:8050
echo "Expense Tracker started. Close this window to keep it running in the background."
