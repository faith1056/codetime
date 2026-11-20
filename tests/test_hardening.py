import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import account_login
import codetime
import tracker_auth


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class HardeningTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def use_home(self, path):
        patcher = mock.patch.dict(os.environ, {"CODETIME_HOME": str(path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_app_folder_is_private(self):
        home = self.root / "new"
        self.use_home(home)
        codetime.connect().close()
        self.assertEqual(mode_of(home), 0o700)

    def test_existing_loose_app_folder_is_tightened(self):
        home = self.root / "loose"
        home.mkdir(mode=0o755)
        os.chmod(home, 0o755)
        self.use_home(home)
        codetime.connect().close()
        self.assertEqual(mode_of(home), 0o700)

    def test_existing_loose_token_file_is_tightened(self):
        home = self.root / "tok"
        home.mkdir()
        self.use_home(home)
        token_file = home / "token"
        token_file.write_text("old-token")
        os.chmod(token_file, 0o644)
        tracker_auth.create_token()
        self.assertEqual(mode_of(token_file), 0o600)

    def _connection(self):
        home = self.root / "login"
        self.use_home(home)
        connection = codetime.connect()
        self.addCleanup(connection.close)
        account_login.ensure_schema(connection)
        return connection

    def _failure_count(self, connection, email):
        return connection.execute(
            "SELECT COUNT(*) FROM failed_logins WHERE email = ?", (email,)
        ).fetchone()[0]

    def test_old_failed_logins_are_purged(self):
        connection = self._connection()
        current = datetime.now(timezone.utc)
        connection.execute(
            "INSERT INTO failed_logins (email, failed_at) VALUES (?, ?)",
            ("old@example.com", (current - timedelta(days=1)).isoformat()),
        )
        connection.commit()
        with self.assertRaises(codetime.CodeTimeError):
            account_login.login(
                connection, "someone@example.com", "wrong-password-1",
                current=current,
            )
        self.assertEqual(self._failure_count(connection, "old@example.com"), 0)
        self.assertEqual(
            self._failure_count(connection, "someone@example.com"), 1
        )

    def test_recent_failed_logins_are_kept(self):
        connection = self._connection()
        current = datetime.now(timezone.utc)
        connection.execute(
            "INSERT INTO failed_logins (email, failed_at) VALUES (?, ?)",
            ("recent@example.com", (current - timedelta(minutes=1)).isoformat()),
        )
        connection.commit()
        with self.assertRaises(codetime.CodeTimeError):
            account_login.login(
                connection, "someone@example.com", "wrong-password-1",
                current=current,
            )
        self.assertEqual(
            self._failure_count(connection, "recent@example.com"), 1
        )


if __name__ == "__main__":
    unittest.main()
