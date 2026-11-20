import os
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

import codetime


class UnscopedCallsNeverSeeAccountRows(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CODETIME_HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.connection = codetime.connect()
        self.addCleanup(self.connection.close)
        self.now = codetime.now()

    def _insert(self, user_id, ended=False):
        started = self.now - timedelta(hours=2)
        end = (self.now - timedelta(hours=1)).isoformat() if ended else None
        cursor = self.connection.execute(
            "INSERT INTO sessions (project, started_at, ended_at, user_id) "
            "VALUES (?, ?, ?, ?)",
            ("proj", started.isoformat(), end, user_id),
        )
        self.connection.commit()
        return cursor.lastrowid

    def test_active_session_ignores_account_rows(self):
        self._insert(user_id=1)
        self.assertIsNone(codetime.active_session(self.connection))

    def test_list_sessions_ignores_account_rows(self):
        self._insert(user_id=1, ended=True)
        self.assertEqual(codetime.list_sessions(self.connection, 10), [])

    def test_get_session_ignores_account_rows(self):
        sid = self._insert(user_id=1, ended=True)
        with self.assertRaises(codetime.CodeTimeError):
            codetime.get_session(self.connection, sid)

    def test_delete_session_cannot_remove_account_rows(self):
        sid = self._insert(user_id=1, ended=True)
        with self.assertRaises(codetime.CodeTimeError):
            codetime.delete_session(self.connection, sid)
        count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_collect_segments_ignores_account_rows(self):
        self._insert(user_id=1, ended=True)
        segments = codetime.collect_segments(
            self.connection,
            self.now - timedelta(days=2),
            self.now + timedelta(days=1),
            self.now,
        )
        self.assertEqual(list(segments), [])

    def test_unowned_rows_are_still_visible(self):
        sid = self._insert(user_id=None)
        self.assertEqual(codetime.active_session(self.connection)[0], sid)


if __name__ == "__main__":
    unittest.main()
