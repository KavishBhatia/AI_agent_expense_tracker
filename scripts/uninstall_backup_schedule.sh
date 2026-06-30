#!/bin/zsh
# Removes the daily backup launchd job.
# Run: bash scripts/uninstall_backup_schedule.sh

PLIST_LABEL="com.expensetracker.backup"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

if [ ! -f "$PLIST_PATH" ]; then
    echo "Backup schedule not installed (plist not found)."
    exit 0
fi

launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm "$PLIST_PATH"
echo "Backup schedule removed."
