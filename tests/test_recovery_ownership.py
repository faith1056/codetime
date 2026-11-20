import os
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

import codetime
import tracker_store

IDLE = timedelta(minutes=5)


class RecoverOwnershipTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CODETIME_HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

        self.connection = codetime.connect()
        self.addCleanup(self.connection.close)

        self.now = codetime.now()
        self.last_seen = self.now - timedelta(hours=1)
        self.started = self.now - timedelta(hours=2)
        tracker_store.write_last_seen(self.last_seen)

    def _insert(self, user_id):
        cursor = self.connection.execute(
            "INSERT INTO sessions (project, started_at, user_id) "
            "VALUES (?, ?, ?)",
            ("proj", self.started.isoformat(), user_id),
        )
        self.connection.commit()
        return cursor.lastrowid

    def _ended(self, session_id):
        return self.connection.execute(
            "SELECT ended_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def test_account_session_is_not_closed(self):
        sid = self._insert(user_id=1)
        result = tracker_store.recover(self.connection, self.now, IDLE)
        self.assertIsNone(result)
        self.assertEqual(self._ended(sid), (None,))

    def test_account_session_is_not_deleted(self):
        self.started = self.last_seen  # the exact-equality delete path
        sid = self._insert(user_id=1)
        result = tracker_store.recover(self.connection, self.now, IDLE)
        self.assertIsNone(result)
        self.assertEqual(self._ended(sid), (None,))

    def test_unowned_session_is_still_recovered(self):
        sid = self._insert(user_id=None)
        result = tracker_store.recover(self.connection, self.now, IDLE)
        self.assertEqual(result, "closed")
        self.assertEqual(self._ended(sid), (self.last_seen.isoformat(),))


if __name__ == "__main__":
    unittest.main()
