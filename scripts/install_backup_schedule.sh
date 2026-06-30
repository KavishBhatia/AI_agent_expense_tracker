#!/bin/zsh
# Installs a daily launchd job that runs backup_db.py at 02:00 every day.
# Run once: bash scripts/install_backup_schedule.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_db.py"
PLIST_LABEL="com.expensetracker.backup"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
LOG_FILE="$HOME/Library/Logs/expense_tracker_backup.log"

if [ ! -f "$PYTHON" ]; then
    echo "Error: virtual environment not found at $PYTHON"
    echo "Run 'uv sync' in the project root first."
    exit 1
fi

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$BACKUP_SCRIPT</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>   <integer>2</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$LOG_FILE</string>
    <key>StandardErrorPath</key>
    <string>$LOG_FILE</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# Unload existing job if present (ignore error if not loaded)
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "Backup schedule installed."
echo "  Runs daily at 02:00"
echo "  Log: $LOG_FILE"
echo ""
echo "To test immediately:"
echo "  launchctl start $PLIST_LABEL"
echo ""
echo "To uninstall:"
echo "  bash $SCRIPT_DIR/uninstall_backup_schedule.sh"
