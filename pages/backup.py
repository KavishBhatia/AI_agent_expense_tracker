# pages/backup.py
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, html

dash.register_page(__name__, path="/backup", name="Backup")

_BACKUP_DIR = Path.home() / "Library" / "Application Support" / "ExpenseTracker" / "backups"
_LOG_FILE = Path.home() / "Library" / "Logs" / "expense_tracker_backup.log"
_SCRIPT = Path(__file__).parents[1] / "scripts" / "backup_db.py"
_TEAL = "#0f766e"
_CARD_STYLE = {"borderTop": f"3px solid {_TEAL}", "borderRadius": "8px"}


def _last_local_backup() -> tuple[str, str]:
    """Return (date_str, filename) of the most recent local backup, or ('Never', '')."""
    if not _BACKUP_DIR.exists():
        return "Never", ""
    files = sorted(_BACKUP_DIR.glob("expenses_*.db"), reverse=True)
    if not files:
        return "Never", ""
    latest = files[0]
    try:
        d = datetime.strptime(latest.stem.replace("expenses_", ""), "%Y-%m-%d")
        return d.strftime("%d %b %Y"), latest.name
    except ValueError:
        return latest.stem, latest.name


def _last_gdrive_backup() -> str:
    """Parse the log file and return the timestamp of the last GDrive upload, or 'Never'."""
    if not _LOG_FILE.exists():
        return "Never"
    try:
        lines = _LOG_FILE.read_text(errors="replace").splitlines()
        for line in reversed(lines):
            if "Google Drive:" in line and ("uploaded" in line or "updated" in line):
                # Log line format: "2026-07-01 02:00:05,123  INFO  Google Drive: uploaded ..."
                ts = line.split("  ")[0].strip()
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
                return dt.strftime("%d %b %Y %H:%M")
        return "Never"
    except Exception:
        return "Unknown"


def _status_card(title: str, value: str, sub: str = "", ok: bool = True):
    colour = _TEAL if ok else "#dc3545"
    card_style = {"borderTop": f"3px solid {colour}", "borderRadius": "8px"}
    children = [
        html.P(title, className="text-muted small mb-1"),
        html.H5(value, className="mb-0"),
    ]
    if sub:
        children.append(html.Small(sub, className="text-muted"))
    return dbc.Col(dbc.Card(dbc.CardBody(children), style=card_style), md=4)


def _build_status():
    local_date, local_file = _last_local_backup()
    gdrive_date = _last_gdrive_backup()
    local_ok = local_date != "Never"
    gdrive_ok = gdrive_date not in ("Never", "Unknown")
    return dbc.Row([
        _status_card("Last Local Backup", local_date, local_file, ok=local_ok),
        _status_card("Last Google Drive Backup", gdrive_date, ok=gdrive_ok),
        _status_card(
            "Backup Location",
            "Local + Google Drive",
            str(_BACKUP_DIR),
            ok=True,
        ),
    ], className="g-3")


layout = html.Div([
    html.H5("Backup", className="mb-1"),
    html.P("Database is backed up daily at 02:00. Run a manual backup anytime.",
           className="text-muted mb-4"),

    # Status cards
    dbc.Card(dbc.CardBody([
        html.H6("Backup Status", className="fw-semibold mb-3"),
        html.Div(id="backup-status-cards", children=_build_status()),
    ]), className="mb-4", style=_CARD_STYLE),

    # Manual backup
    dbc.Card(dbc.CardBody([
        html.H6("Manual Backup", className="fw-semibold mb-2"),
        html.P(
            "Copies the database to the local backup folder and uploads to Google Drive.",
            className="text-muted small mb-3",
        ),
        dbc.Row([
            dbc.Col(
                dbc.Button("Back Up Now", id="backup-run-btn", color="primary", n_clicks=0),
                width="auto",
            ),
            dbc.Col(
                dbc.Button("Local Only", id="backup-local-btn", color="outline-secondary",
                           n_clicks=0),
                width="auto",
            ),
        ], className="g-2 mb-3"),
        html.Div(id="backup-run-output"),
    ]), className="mb-4", style=_CARD_STYLE),

    # Schedule info
    dbc.Card(dbc.CardBody([
        html.H6("Schedule", className="fw-semibold mb-2"),
        html.P("Runs daily at 02:00 via macOS launchd.", className="text-muted small mb-2"),
        dbc.Row([
            dbc.Col(
                html.Code("bash scripts/install_backup_schedule.sh",
                          style={"fontSize": "13px"}),
            ),
        ], className="mb-1"),
        html.Small("Run the above once from the project root to install the schedule.",
                   className="text-muted"),
    ]), style=_CARD_STYLE),
])


def _run_backup(local_only: bool) -> tuple[bool, str]:
    cmd = [sys.executable, str(_SCRIPT)]
    if local_only:
        cmd.append("--local")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output or "Backup complete."
    except subprocess.TimeoutExpired:
        return False, "Backup timed out after 60 seconds."
    except Exception as exc:
        return False, f"Error: {exc}"


@callback(
    Output("backup-run-output", "children"),
    Output("backup-status-cards", "children"),
    Input("backup-run-btn", "n_clicks"),
    Input("backup-local-btn", "n_clicks"),
    prevent_initial_call=True,
)
def run_backup(n_full, n_local):
    local_only = dash.callback_context.triggered_id == "backup-local-btn"
    ok, message = _run_backup(local_only)
    alert = dbc.Alert(
        message,
        color="success" if ok else "danger",
        dismissable=True,
        className="small",
        style={"whiteSpace": "pre-wrap"},
    )
    return alert, _build_status()
