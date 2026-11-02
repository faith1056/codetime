import os
import tempfile
import unittest
from datetime import datetime, timedelta

import codetime
import tracker_store

BASE = datetime(2026, 11, 3, 9, 0, 0)
LIMIT = timedelta(minutes=5)


def t(minutes=0):
    return BASE + timedelta(minutes=minutes)


class TestRecovery(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.connection = codetime.connect()

    def tearDown(self):
        self.connection.close()
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def add_open_row(self, started):
        self.connection.execute(
            "INSERT INTO sessions (project, started_at) VALUES (?, ?)",
            ("alpha", started.isoformat()),
        )
        self.connection.commit()

    def rows(self):
        return self.connection.execute(
            "SELECT project, started_at, ended_at FROM sessions ORDER BY id"
        ).fetchall()

    def test_crash_leftover_is_closed_at_last_seen(self):
        self.add_open_row(t(0))
        tracker_store.write_last_seen(t(20))
        result = tracker_store.recover(self.connection, t(60), LIMIT)
        self.assertEqual(result, "closed")
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(20).isoformat())]
        )

    def test_never_closed_at_current_time(self):
        self.add_open_row(t(0))
        tracker_store.write_last_seen(t(20))
        tracker_store.recover(self.connection, t(500), LIMIT)
        self.assertEqual(self.rows()[0][2], t(20).isoformat())

    def test_zero_length_leftover_is_deleted(self):
        self.add_open_row(t(20))
        tracker_store.write_last_seen(t(20))
        result = tracker_store.recover(self.connection, t(60), LIMIT)
        self.assertEqual(result, "deleted")
        self.assertEqual(self.rows(), [])

    def test_recent_last_seen_is_left_alone(self):
        self.add_open_row(t(0))
        tracker_store.write_last_seen(t(20))
        result = tracker_store.recover(self.connection, t(24), LIMIT)
        self.assertIsNone(result)
        self.assertIsNone(self.rows()[0][2])

    def test_manual_session_started_after_last_seen_is_left_alone(self):
        tracker_store.write_last_seen(t(20))
        self.add_open_row(t(30))
        result = tracker_store.recover(self.connection, t(90), LIMIT)
        self.assertIsNone(result)
        self.assertIsNone(self.rows()[0][2])

    def test_no_last_seen_file_leaves_row_alone(self):
        self.add_open_row(t(0))
        result = tracker_store.recover(self.connection, t(90), LIMIT)
        self.assertIsNone(result)
        self.assertIsNone(self.rows()[0][2])

    def test_corrupt_last_seen_file_leaves_row_alone(self):
        self.add_open_row(t(0))
        tracker_store.last_seen_path().write_text("not a time")
        result = tracker_store.recover(self.connection, t(90), LIMIT)
        self.assertIsNone(result)
        self.assertIsNone(self.rows()[0][2])

    def test_no_open_row_does_nothing(self):
        tracker_store.write_last_seen(t(20))
        result = tracker_store.recover(self.connection, t(90), LIMIT)
        self.assertIsNone(result)
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
