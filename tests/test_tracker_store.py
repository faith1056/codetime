import os
import tempfile
import unittest
from datetime import datetime, timedelta

import codetime
from tracker_state import Action
from tracker_store import Store

BASE = datetime(2026, 11, 3, 9, 0, 0)


def t(minutes=0):
    return BASE + timedelta(minutes=minutes)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.connection = codetime.connect()
        self.store = Store(self.connection)

    def tearDown(self):
        self.connection.close()
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def rows(self):
        return self.connection.execute(
            "SELECT project, started_at, ended_at FROM sessions ORDER BY id"
        ).fetchall()

    def test_open_inserts_an_open_row(self):
        self.store.apply([Action("open", "alpha", t(0))], t(1))
        self.assertEqual(self.rows(), [("alpha", t(0).isoformat(), None)])

    def test_close_sets_ended_at(self):
        self.store.apply([Action("open", "alpha", t(0))], t(1))
        self.store.apply([Action("close", "alpha", t(5))], t(6))
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(5).isoformat())]
        )

    def test_zero_length_row_is_deleted(self):
        self.store.apply([Action("open", "alpha", t(0))], t(1))
        self.store.apply([Action("close", "alpha", t(0))], t(1))
        self.assertEqual(self.rows(), [])

    def test_manual_session_blocks_the_tracker(self):
        codetime.start_session(self.connection, "manual")
        self.store.apply([Action("open", "alpha", t(0))], t(1))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0][0], "manual")

    def test_close_after_codetime_stop_does_nothing(self):
        self.store.apply([Action("open", "alpha", t(0))], t(1))
        self.connection.execute(
            "UPDATE sessions SET ended_at = ?", (t(3).isoformat(),)
        )
        self.connection.commit()
        self.store.apply([Action("close", "alpha", t(5))], t(6))
        self.assertEqual(self.rows()[0][2], t(3).isoformat())

    def test_close_time_is_never_in_the_future(self):
        self.store.apply([Action("open", "alpha", t(0))], t(1))
        self.store.apply([Action("close", "alpha", t(30))], t(10))
        self.assertEqual(self.rows()[0][2], t(10).isoformat())

    def test_close_without_open_does_nothing(self):
        self.store.apply([Action("close", "alpha", t(5))], t(6))
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
