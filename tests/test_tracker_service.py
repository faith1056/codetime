import os
import stat
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta

import codetime
import tracker_auth
import tracker_service
import tracker_store
from tracker_engine import Engine

BASE = datetime(2026, 11, 3, 9, 0, 0)


def t(minutes=0):
    return BASE + timedelta(minutes=minutes)


class TestService(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.engine = Engine()
        self.lock = threading.Lock()

    def tearDown(self):
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def rows(self):
        with closing(codetime.connect()) as connection:
            return connection.execute(
                "SELECT project, started_at, ended_at FROM sessions "
                "ORDER BY id"
            ).fetchall()

    def test_startup_creates_owner_only_token(self):
        tracker_service.startup(self.engine, self.lock, t(0))
        mode = stat.S_IMODE(os.stat(tracker_auth.token_path()).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertIsNotNone(tracker_auth.load_token())

    def test_startup_reuses_existing_token(self):
        first = tracker_auth.create_token()
        tracker_service.startup(self.engine, self.lock, t(0))
        self.assertEqual(tracker_auth.load_token(), first)

    def test_startup_recovers_a_crash_leftover(self):
        with closing(codetime.connect()) as connection:
            connection.execute(
                "INSERT INTO sessions (project, started_at) VALUES (?, ?)",
                ("alpha", t(0).isoformat()),
            )
            connection.commit()
        tracker_store.write_last_seen(t(20))
        result = tracker_service.startup(self.engine, self.lock, t(60))
        self.assertEqual(result, "closed")
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(20).isoformat())]
        )

    def test_startup_leaves_a_manual_session_alone(self):
        with closing(codetime.connect()) as connection:
            codetime.start_session(connection, "manual")
        result = tracker_service.startup(self.engine, self.lock, t(60))
        self.assertIsNone(result)
        self.assertIsNone(self.rows()[0][2])

    def test_tick_closes_an_idle_row_at_last_activity(self):
        with closing(codetime.connect()) as connection:
            self.engine.activity(connection, "alpha", t(0))
            self.engine.activity(connection, "alpha", t(2))
        tracker_service.tick_once(self.engine, self.lock, t(8))
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(2).isoformat())]
        )

    def test_tick_before_idle_limit_changes_nothing(self):
        with closing(codetime.connect()) as connection:
            self.engine.activity(connection, "alpha", t(0))
        tracker_service.tick_once(self.engine, self.lock, t(4))
        self.assertIsNone(self.rows()[0][2])


if __name__ == "__main__":
    unittest.main()
