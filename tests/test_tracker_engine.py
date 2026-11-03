import os
import tempfile
import unittest
from datetime import datetime, timedelta

import codetime
import tracker_store
from tracker_engine import Engine

BASE = datetime(2026, 11, 3, 9, 0, 0)


def t(minutes=0):
    return BASE + timedelta(minutes=minutes)


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.connection = codetime.connect()
        self.engine = Engine(self.connection)

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

    def test_activity_opens_a_row_and_writes_last_seen(self):
        self.engine.activity("alpha", t(0))
        self.assertEqual(self.rows(), [("alpha", t(0).isoformat(), None)])
        self.assertEqual(tracker_store.read_last_seen(), t(0))

    def test_repeated_activity_keeps_one_row(self):
        self.engine.activity("alpha", t(0))
        self.engine.activity("alpha", t(1))
        self.engine.activity("alpha", t(2))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(tracker_store.read_last_seen(), t(2))

    def test_tick_closes_row_at_last_activity_when_idle(self):
        self.engine.activity("alpha", t(0))
        self.engine.activity("alpha", t(2))
        self.engine.tick(t(8))
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(2).isoformat())]
        )
        self.assertIsNone(tracker_store.read_last_seen())

    def test_tick_before_idle_limit_changes_nothing(self):
        self.engine.activity("alpha", t(0))
        self.engine.tick(t(4))
        self.assertIsNone(self.rows()[0][2])

    def test_switching_project_makes_two_rows(self):
        self.engine.activity("alpha", t(0))
        self.engine.activity("beta", t(3))
        self.assertEqual(
            self.rows(),
            [
                ("alpha", t(0).isoformat(), t(3).isoformat()),
                ("beta", t(3).isoformat(), None),
            ],
        )

    def test_activity_after_idle_starts_a_new_row(self):
        self.engine.activity("alpha", t(0))
        self.engine.activity("alpha", t(2))
        self.engine.tick(t(6))
        self.engine.activity("alpha", t(20))
        self.assertEqual(len(self.rows()), 2)
        self.assertIsNone(self.rows()[1][2])

    def test_pause_closes_row_and_ignores_activity(self):
        self.engine.activity("alpha", t(0))
        self.engine.pause(t(2))
        self.engine.activity("alpha", t(3))
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(2).isoformat())]
        )
        self.assertIsNone(tracker_store.read_last_seen())

    def test_stop_closes_row_and_clears_last_seen(self):
        self.engine.activity("alpha", t(0))
        self.engine.stop(t(4))
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(4).isoformat())]
        )
        self.assertIsNone(tracker_store.read_last_seen())

    def test_start_recovers_a_crash_leftover(self):
        self.engine.activity("alpha", t(0))
        self.engine.activity("alpha", t(4))
        self.connection.close()

        self.connection = codetime.connect()
        new_engine = Engine(self.connection)
        result = new_engine.start(t(60))
        self.assertEqual(result, "closed")
        self.assertEqual(
            self.rows(), [("alpha", t(0).isoformat(), t(4).isoformat())]
        )


if __name__ == "__main__":
    unittest.main()
