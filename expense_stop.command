#!/bin/bash
# Double-click this file in Finder to stop the Expense Tracker app.
# It stops the app, then closes the Terminal windows used to start and stop it.
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd -P)"
PID_FILE="$PROJECT_DIR/.expense_tracker.pid"
TTY_FILE="$PROJECT_DIR/.expense_tracker.tty"
PORT="${EXPENSE_PORT:-8050}"

MY_TTY="$(tty 2>/dev/null)"
[[ "$MY_TTY" == /dev/* ]] || MY_TTY=""

# Wait up to ~5 s for a process to exit.
wait_gone() {
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 "$1" 2>/dev/null || return 0
        sleep 0.5
    done
    return 1
}

stop_pid() {
    kill "$1" 2>/dev/null
    if wait_gone "$1"; then
        return 0
    fi
    echo "Process $1 did not exit after SIGTERM; it may still be running."
    return 1
}

# True if the PID is a python process whose working directory is this project.
is_project_python() {
    local pid="$1" cwd comm
    comm="$(ps -o comm= -p "$pid" 2>/dev/null)"
    [[ "$comm" == *[Pp]ython* ]] || return 1
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    [ "$cwd" = "$PROJECT_DIR" ]
}

stopped=0

# 1. Stop the app recorded in the PID file.
if [ -f "$PID_FILE" ]; then
    read -r PID < "$PID_FILE" || PID=""
    if [[ "$PID" =~ ^[1-9][0-9]*$ ]] && kill -0 "$PID" 2>/dev/null; then
        if stop_pid "$PID"; then
            stopped=1
            echo "Expense Tracker stopped."
        fi
    fi
fi

# 2. Fallback: something from this project is still listening on the port.
if [ "$stopped" -eq 0 ]; then
    for pid in $(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null); do
        if is_project_python "$pid"; then
            if stop_pid "$pid"; then
                stopped=1
                echo "Expense Tracker stopped (found on port $PORT)."
            fi
        fi
    done
fi

if [ "$stopped" -eq 0 ]; then
    echo "Expense Tracker is not running."
fi

# 3. Close the Terminal windows (Terminal.app only). The start window is closed
# only if the app was actually running, so a stale tty that Terminal has since
# reused for another window is never closed by mistake.
TTYS=()
[ -n "$MY_TTY" ] && TTYS+=("$MY_TTY")
if [ "$stopped" -eq 1 ] && [ -f "$TTY_FILE" ]; then
    read -r START_TTY < "$TTY_FILE" || START_TTY=""
    [[ "$START_TTY" == /dev/* ]] && TTYS+=("$START_TTY")
fi
rm -f "$PID_FILE" "$TTY_FILE"

if [ "$TERM_PROGRAM" = "Apple_Terminal" ] && [ "${#TTYS[@]}" -gt 0 ]; then
    # Window ids are collected first and closed by id, because closing by list
    # position skips windows once an earlier one has closed.
    # Detached into its own session (no controlling tty) and delayed, so that
    # Terminal does not see a running process and ask before closing the window.
    perl -MPOSIX -e '
        exit if fork;
        POSIX::setsid();
        open STDIN, "<", "/dev/null"; open STDOUT, ">", "/dev/null"; open STDERR, ">", "/dev/null";
        sleep 1;
        exec @ARGV;
    ' osascript \
        -e 'on run argv' \
        -e 'tell application "Terminal"' \
        -e 'set ids to {}' \
        -e 'repeat with w in (windows)' \
        -e 'repeat with t in (tabs of w)' \
        -e 'if argv contains (tty of t) then set end of ids to (id of w)' \
        -e 'end repeat' \
        -e 'end repeat' \
        -e 'repeat with i in ids' \
        -e 'try' \
        -e 'close (window id (contents of i))' \
        -e 'end try' \
        -e 'end repeat' \
        -e 'end tell' \
        -e 'end run' \
        "${TTYS[@]}"
fi
