# tests/test_backup_script.py
"""Tests for scripts/backup_db.py.

The script configures logging and creates ~/Library/Logs at import time, so it is
loaded here with HOME pointed at a temp dir: importing it must never touch the
real log file, backups or Google credentials.
"""
import atexit
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

_FAKE_HOME = tempfile.mkdtemp(prefix="backup_test_home_")
atexit.register(shutil.rmtree, _FAKE_HOME, ignore_errors=True)


def _load_backup_module():
    path = Path(__file__).parents[1] / "scripts" / "backup_db.py"
    spec = importlib.util.spec_from_file_location("backup_db_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"HOME": _FAKE_HOME}):
        spec.loader.exec_module(module)
    return module


backup = _load_backup_module()


def _make_db(path: Path, rows=(("a", 1.0),)) -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.execute("CREATE TABLE t (name TEXT, amount REAL)")
        conn.executemany("INSERT INTO t VALUES (?, ?)", rows)


def _read_rows(path: Path):
    with sqlite3.connect(str(path)) as conn:
        return conn.execute("SELECT name, amount FROM t ORDER BY name").fetchall()


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backup_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.backup_dir = self.tmp / "backups"
        self.db = self.tmp / "expenses.db"
        self.trips_db = self.tmp / "trips.db"
        for name, value in (
            ("BACKUP_DIR", self.backup_dir),
            ("DB_PATH", self.db),
            ("TRIPS_DB_PATH", self.trips_db),
            ("TOKEN_PATH", self.tmp / "gdrive_token.json"),
            ("CREDENTIALS_PATH", self.tmp / "credentials.json"),
            ("CONFIG_DIR", self.tmp / "config"),
        ):
            p = patch.object(backup, name, value)
            p.start()
            self.addCleanup(p.stop)


class TestModuleImportIsSideEffectSafe(unittest.TestCase):
    def test_paths_resolved_under_fake_home_not_real_home(self):
        self.assertTrue(str(backup.LOG_FILE).startswith(_FAKE_HOME))
        self.assertTrue(str(backup.BACKUP_DIR).startswith(_FAKE_HOME))
        self.assertTrue(str(backup.CONFIG_DIR).startswith(_FAKE_HOME))


class TestLocalBackup(BackupTestCase):
    def test_creates_dated_copy_with_same_data(self):
        _make_db(self.db, rows=(("a", 1.0), ("b", 2.5)))
        dest = backup._local_backup()
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(dest, self.backup_dir / f"expenses_{today}.db")
        self.assertEqual(_read_rows(dest), [("a", 1.0), ("b", 2.5)])

    def test_creates_backup_dir_if_missing(self):
        _make_db(self.db)
        self.assertFalse(self.backup_dir.exists())
        backup._local_backup()
        self.assertTrue(self.backup_dir.is_dir())

    def test_same_day_rerun_overwrites_with_current_data(self):
        _make_db(self.db, rows=(("a", 1.0),))
        backup._local_backup()
        with sqlite3.connect(str(self.db)) as conn:
            conn.execute("INSERT INTO t VALUES ('b', 2.0)")
        dest = backup._local_backup()
        self.assertEqual(_read_rows(dest), [("a", 1.0), ("b", 2.0)])

    def test_original_database_is_untouched(self):
        _make_db(self.db, rows=(("a", 1.0),))
        backup._local_backup()
        self.assertEqual(_read_rows(self.db), [("a", 1.0)])


class TestLocalBackupTrips(BackupTestCase):
    def test_returns_none_when_trips_db_absent(self):
        self.assertIsNone(backup._local_backup_trips())
        self.assertFalse(self.backup_dir.exists())

    def test_backs_up_trips_db_when_present(self):
        _make_db(self.trips_db, rows=(("Rome", 3.0),))
        dest = backup._local_backup_trips()
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(dest, self.backup_dir / f"trips_{today}.db")
        self.assertEqual(_read_rows(dest), [("Rome", 3.0)])


class TestPruneOldBackups(BackupTestCase):
    def _touch(self, name: str) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        f = self.backup_dir / name
        f.write_text("x")
        return f

    @staticmethod
    def _stamp(days_ago: int) -> str:
        return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def test_removes_old_expenses_and_trips_backups_keeps_recent(self):
        old_e = self._touch(f"expenses_{self._stamp(backup.KEEP_DAYS + 5)}.db")
        old_t = self._touch(f"trips_{self._stamp(backup.KEEP_DAYS + 5)}.db")
        new_e = self._touch(f"expenses_{self._stamp(backup.KEEP_DAYS - 5)}.db")
        new_t = self._touch(f"trips_{self._stamp(1)}.db")
        backup._prune_old_backups()
        self.assertFalse(old_e.exists())
        self.assertFalse(old_t.exists())
        self.assertTrue(new_e.exists())
        self.assertTrue(new_t.exists())

    def test_ignores_files_that_do_not_match_the_date_pattern(self):
        odd = self._touch("expenses_notadate.db")
        other = self._touch("other_2000-01-01.db")
        backup._prune_old_backups()
        self.assertTrue(odd.exists())
        self.assertTrue(other.exists())

    def test_empty_directory_is_fine(self):
        self.backup_dir.mkdir()
        backup._prune_old_backups()  # must not raise


class TestEnsureGdriveFolder(unittest.TestCase):
    def _service(self, existing):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": existing}
        service.files.return_value.create.return_value.execute.return_value = {"id": "new-id"}
        return service

    def test_returns_existing_folder_id_without_creating(self):
        service = self._service([{"id": "abc"}])
        self.assertEqual(backup._ensure_gdrive_folder(service), "abc")
        service.files.return_value.create.assert_not_called()

    def test_creates_folder_when_missing(self):
        service = self._service([])
        self.assertEqual(backup._ensure_gdrive_folder(service), "new-id")
        body = service.files.return_value.create.call_args.kwargs["body"]
        self.assertEqual(body["name"], backup.GDRIVE_FOLDER_NAME)
        self.assertEqual(body["mimeType"], "application/vnd.google-apps.folder")


class TestUploadToGdrive(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.local = self.tmp / "expenses_2026-01-01.db"
        _make_db(self.local)

    def _service(self, existing):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": existing}
        return service

    def test_does_nothing_when_not_authenticated(self):
        with patch.object(backup, "_get_gdrive_service", return_value=None), \
             patch.object(backup, "_ensure_gdrive_folder") as ensure:
            backup._upload_to_gdrive(self.local)
        ensure.assert_not_called()

    def test_creates_file_in_folder_when_new(self):
        service = self._service([])
        with patch.object(backup, "_get_gdrive_service", return_value=service), \
             patch.object(backup, "_ensure_gdrive_folder", return_value="folder-1"):
            backup._upload_to_gdrive(self.local)
        files = service.files.return_value
        files.create.assert_called_once()
        body = files.create.call_args.kwargs["body"]
        self.assertEqual(body, {"name": self.local.name, "parents": ["folder-1"]})
        files.update.assert_not_called()

    def test_updates_existing_file_on_same_day_rerun(self):
        service = self._service([{"id": "file-9"}])
        with patch.object(backup, "_get_gdrive_service", return_value=service), \
             patch.object(backup, "_ensure_gdrive_folder", return_value="folder-1"):
            backup._upload_to_gdrive(self.local)
        files = service.files.return_value
        files.update.assert_called_once()
        self.assertEqual(files.update.call_args.kwargs["fileId"], "file-9")
        files.create.assert_not_called()


class TestGetGdriveService(BackupTestCase):
    def _creds(self, *, valid=True, expired=False, refresh_token="r"):
        creds = MagicMock()
        creds.valid = valid
        creds.expired = expired
        creds.refresh_token = refresh_token
        creds.to_json.return_value = '{"token": "refreshed"}'
        return creds

    def test_returns_none_when_no_token_file(self):
        with patch("googleapiclient.discovery.build") as build:
            self.assertIsNone(backup._get_gdrive_service())
        build.assert_not_called()

    def test_valid_token_builds_drive_service(self):
        backup.TOKEN_PATH.write_text("{}")
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file",
                   return_value=self._creds()), \
             patch("googleapiclient.discovery.build", return_value="service") as build:
            self.assertEqual(backup._get_gdrive_service(), "service")
        self.assertEqual(build.call_args.args[:2], ("drive", "v3"))

    def test_expired_token_is_refreshed_and_saved(self):
        backup.TOKEN_PATH.write_text("{}")
        creds = self._creds(valid=True, expired=True)
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file",
                   return_value=creds), \
             patch("googleapiclient.discovery.build", return_value="service"):
            self.assertEqual(backup._get_gdrive_service(), "service")
        creds.refresh.assert_called_once()
        self.assertEqual(backup.TOKEN_PATH.read_text(), '{"token": "refreshed"}')

    def test_refresh_failure_returns_none_and_keeps_old_token(self):
        backup.TOKEN_PATH.write_text('{"old": true}')
        creds = self._creds(expired=True)
        creds.refresh.side_effect = RuntimeError("revoked")
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file",
                   return_value=creds), \
             patch("googleapiclient.discovery.build") as build:
            self.assertIsNone(backup._get_gdrive_service())
        build.assert_not_called()
        self.assertEqual(backup.TOKEN_PATH.read_text(), '{"old": true}')

    def test_invalid_creds_without_refresh_returns_none(self):
        backup.TOKEN_PATH.write_text("{}")
        creds = self._creds(valid=False, expired=True, refresh_token=None)
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file",
                   return_value=creds), \
             patch("googleapiclient.discovery.build") as build:
            self.assertIsNone(backup._get_gdrive_service())
        build.assert_not_called()


class TestRunAuth(BackupTestCase):
    def test_missing_credentials_file_exits_with_instructions(self):
        with patch("builtins.print") as printed:
            with self.assertRaises(SystemExit) as cm:
                backup._run_auth()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Credentials file not found", printed.call_args_list[0].args[0])

    def test_success_saves_token(self):
        backup.CREDENTIALS_PATH.write_text("{}")
        flow = MagicMock()
        flow.run_local_server.return_value.to_json.return_value = '{"token": "t"}'
        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
                   return_value=flow) as from_secrets, \
             patch("builtins.print"):
            backup._run_auth()
        from_secrets.assert_called_once_with(str(backup.CREDENTIALS_PATH), backup.SCOPES)
        self.assertEqual(backup.TOKEN_PATH.read_text(), '{"token": "t"}')


class TestMain(BackupTestCase):
    def _run_main(self, *argv):
        with patch.object(sys, "argv", ["backup_db.py", *argv]):
            backup.main()

    def test_auth_flag_runs_auth_only(self):
        with patch.object(backup, "_run_auth") as run_auth, \
             patch.object(backup, "_local_backup") as local:
            self._run_main("--auth")
        run_auth.assert_called_once()
        local.assert_not_called()

    def test_missing_database_exits_with_error(self):
        with patch.object(backup, "_local_backup") as local:
            with self.assertRaises(SystemExit) as cm:
                self._run_main()
        self.assertEqual(cm.exception.code, 1)
        local.assert_not_called()

    def test_local_flag_skips_google_drive(self):
        _make_db(self.db)
        with patch.object(backup, "_upload_to_gdrive") as upload:
            self._run_main("--local")
        upload.assert_not_called()
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertTrue((self.backup_dir / f"expenses_{today}.db").exists())

    def test_default_run_uploads_expenses_and_trips(self):
        _make_db(self.db)
        _make_db(self.trips_db)
        with patch.object(backup, "_upload_to_gdrive") as upload:
            self._run_main()
        names = [c.args[0].name for c in upload.call_args_list]
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(names, [f"expenses_{today}.db", f"trips_{today}.db"])

    def test_default_run_without_trips_db_uploads_only_expenses(self):
        _make_db(self.db)
        with patch.object(backup, "_upload_to_gdrive") as upload:
            self._run_main()
        self.assertEqual(upload.call_count, 1)

    def test_prunes_old_backups_on_every_run(self):
        _make_db(self.db)
        with patch.object(backup, "_prune_old_backups") as prune:
            self._run_main("--local")
        prune.assert_called_once()


if __name__ == "__main__":
    unittest.main()
