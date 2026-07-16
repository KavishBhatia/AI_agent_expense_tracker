#!/usr/bin/env python3
"""
Daily backup script for expenses.db and trips.db.

Usage:
  python scripts/backup_db.py          # run backup (local + Google Drive)
  python scripts/backup_db.py --auth   # complete OAuth flow (first-time setup)
  python scripts/backup_db.py --local  # local backup only, skip Google Drive

Google Drive setup (one-time):
  1. Go to https://console.cloud.google.com/
  2. Create a project (or select existing one)
  3. Enable the Google Drive API:
       APIs & Services → Enable APIs → search "Google Drive API" → Enable
  4. Create OAuth credentials:
       APIs & Services → Credentials → Create Credentials → OAuth client ID
       Application type: Desktop app
       Name: ExpenseTracker Backup
  5. Download the credentials JSON → save as:
       ~/.config/expense_tracker/credentials.json
  6. Run: python scripts/backup_db.py --auth
       This opens a browser, you log in, and the token is saved automatically.
  After that, daily backups run fully unattended.
"""

import argparse
import logging
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parents[1]
DB_PATH = PROJECT_ROOT / "expenses.db"
TRIPS_DB_PATH = PROJECT_ROOT / "trips.db"

BACKUP_DIR = Path.home() / "Library" / "Application Support" / "ExpenseTracker" / "backups"
LOG_FILE = Path.home() / "Library" / "Logs" / "expense_tracker_backup.log"
CONFIG_DIR = Path.home() / ".config" / "expense_tracker"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
TOKEN_PATH = CONFIG_DIR / "gdrive_token.json"

GDRIVE_FOLDER_NAME = "ExpenseTrackerBackups"
KEEP_DAYS = 30
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Local backup ──────────────────────────────────────────────────────────────

def _local_backup() -> Path:
    """Create a consistent SQLite backup in the backup directory with today's date stamp."""
    import sqlite3

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    dest = BACKUP_DIR / f"expenses_{today}.db"
    with sqlite3.connect(str(DB_PATH)) as src, sqlite3.connect(str(dest)) as dst:
        src.backup(dst)
    log.info("Local backup saved: %s", dest)
    return dest


def _local_backup_trips() -> Path | None:
    """Back up trips.db if it exists. Returns the backup path, or None if trips.db is absent."""
    import sqlite3

    if not TRIPS_DB_PATH.exists():
        log.info("trips.db not found — skipping trips backup")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    dest = BACKUP_DIR / f"trips_{today}.db"
    with sqlite3.connect(str(TRIPS_DB_PATH)) as src, sqlite3.connect(str(dest)) as dst:
        src.backup(dst)
    log.info("Local trips backup saved: %s", dest)
    return dest


def _prune_old_backups() -> None:
    """Delete local backups older than KEEP_DAYS days (both expenses and trips)."""
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for prefix in ("expenses", "trips"):
        for f in BACKUP_DIR.glob(f"{prefix}_*.db"):
            try:
                file_date = datetime.strptime(f.stem.replace(f"{prefix}_", ""), "%Y-%m-%d")
                if file_date < cutoff:
                    f.unlink()
                    log.info("Pruned old backup: %s", f.name)
            except ValueError:
                pass  # skip files that don't match the naming pattern


# ── Google Drive ──────────────────────────────────────────────────────────────

def _get_gdrive_service():
    """Return an authenticated Google Drive service, refreshing token if needed."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        log.error(
            "Google Drive libraries not installed. Run:\n"
            "  uv sync\n"
            "or: pip install google-auth-oauthlib google-api-python-client"
        )
        return None

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            log.exception("Failed to refresh Google Drive token; re-run with --auth.")
            return None
        TOKEN_PATH.write_text(creds.to_json())

    if not creds or not creds.valid:
        log.error(
            "Google Drive not authenticated. Run once:\n"
            "  python scripts/backup_db.py --auth"
        )
        return None

    return build("drive", "v3", credentials=creds)


def _ensure_gdrive_folder(service) -> str:
    """Return the Google Drive folder ID, creating the folder if it doesn't exist."""
    query = (
        f"name='{GDRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder'"
        " and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]

    folder = service.files().create(
        body={"name": GDRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    log.info("Created Google Drive folder: %s", GDRIVE_FOLDER_NAME)
    return folder["id"]


def _upload_to_gdrive(local_file: Path) -> None:
    """Upload local_file to the ExpenseTrackerBackups folder on Google Drive."""
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return

    service = _get_gdrive_service()
    if not service:
        return

    folder_id = _ensure_gdrive_folder(service)

    # Overwrite if a file with the same name already exists (same-day re-run)
    existing = service.files().list(
        q=f"name='{local_file.name}' and '{folder_id}' in parents and trashed=false",
        fields="files(id)",
    ).execute().get("files", [])

    media = MediaFileUpload(str(local_file), mimetype="application/x-sqlite3", resumable=False)
    if existing:
        service.files().update(fileId=existing[0]["id"], media_body=media).execute()
        log.info("Google Drive: updated %s", local_file.name)
    else:
        service.files().create(
            body={"name": local_file.name, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        log.info("Google Drive: uploaded %s", local_file.name)


# ── Auth flow ─────────────────────────────────────────────────────────────────

def _run_auth() -> None:
    """Interactive OAuth2 flow — run once to authorise Google Drive access."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing dependency. Run: uv sync")
        sys.exit(1)

    if not CREDENTIALS_PATH.exists():
        print(
            "\nCredentials file not found.\n\n"
            "Follow these steps:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. Create or select a project\n"
            "  3. Enable the Google Drive API:\n"
            "       APIs & Services → Enable APIs → search 'Google Drive API' → Enable\n"
            "  4. Create OAuth credentials:\n"
            "       APIs & Services → Credentials → Create Credentials → OAuth client ID\n"
            "       Application type: Desktop app\n"
            "  5. Download the JSON → save as:\n"
            f"       {CREDENTIALS_PATH}\n"
            "  6. Re-run: python scripts/backup_db.py --auth\n"
        )
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"\nAuthentication successful. Token saved to:\n  {TOKEN_PATH}")
    print("\nYou can now run backups without --auth.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backup expenses.db locally and to Google Drive")
    parser.add_argument("--auth", action="store_true", help="Complete Google Drive OAuth flow")
    parser.add_argument("--local", action="store_true", help="Local backup only, skip Google Drive")
    args = parser.parse_args()

    if args.auth:
        _run_auth()
        return

    if not DB_PATH.exists():
        log.error("Database not found: %s", DB_PATH)
        sys.exit(1)

    log.info("=== Expense Tracker backup started ===")
    local_file = _local_backup()
    local_trips_file = _local_backup_trips()
    _prune_old_backups()

    if not args.local:
        _upload_to_gdrive(local_file)
        if local_trips_file:
            _upload_to_gdrive(local_trips_file)

    log.info("=== Backup complete ===")


if __name__ == "__main__":
    main()
