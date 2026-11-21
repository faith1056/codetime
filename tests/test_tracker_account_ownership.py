import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import account_login
import accounts
import codetime
from tracker_engine import Engine


BASE = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
PASSWORD = "correct horse battery"


class TestTrackerAccountOwnership(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.connection = codetime.connect()
        account_login.ensure_schema(self.connection)
        self.ada = accounts.register(
            self.connection, "ada@example.com", PASSWORD
        )
        self.bob = accounts.register(
            self.connection, "bob@example.com", PASSWORD
        )
        self.engine = Engine()

    def tearDown(self):
        self.connection.close()
        if self.old_home is None:
            os.environ.pop("CODETIME_HOME", None)
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def rows(self):
        return self.connection.execute(
            "SELECT project, user_id, started_at, ended_at "
            "FROM sessions ORDER BY id"
        ).fetchall()

    def test_automatic_session_is_owned_by_the_active_account(self):
        self.engine.activity(
            self.connection, "alpha", BASE, user_id=self.ada
        )
        self.assertEqual(
            self.rows(),
            [("alpha", self.ada, BASE.isoformat(), None)],
        )

    def test_switching_accounts_closes_only_the_previous_owned_session(self):
        self.engine.activity(
            self.connection, "alpha", BASE, user_id=self.ada
        )
        self.engine.activity(
            self.connection, "beta", BASE + timedelta(minutes=2),
            user_id=self.bob,
        )
        self.assertEqual(
            self.rows(),
            [
                ("alpha", self.ada, BASE.isoformat(),
                 (BASE + timedelta(minutes=2)).isoformat()),
                ("beta", self.bob, (BASE + timedelta(minutes=2)).isoformat(),
                 None),
            ],
        )

    def test_account_owned_session_is_not_closed_by_another_account(self):
        self.connection.execute(
            "INSERT INTO sessions (project, started_at, user_id) "
            "VALUES (?, ?, ?)",
            ("bob-private", BASE.isoformat(), self.bob),
        )
        self.connection.commit()
        self.engine.activity(
            self.connection, "ada-project", BASE, user_id=self.ada
        )
        self.assertEqual(
            self.rows(),
            [
                ("bob-private", self.bob, BASE.isoformat(), None),
                ("ada-project", self.ada, BASE.isoformat(), None),
            ],
        )


if __name__ == "__main__":
    unittest.main()
