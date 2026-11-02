"""Apply tracker Actions to the existing CodeTime sessions table."""

from datetime import datetime

import codetime


class Store:
    def __init__(self, connection):
        self.connection = connection
        self.open_id = None  # the row this tracker opened, if any

    def apply(self, actions, current):
        for action in actions:
            if action.kind == "open":
                self._open(action)
            elif action.kind == "close":
                self._close(action, current)

    def _open(self, action):
        # Never open a row while another one (e.g. a manual session) is open.
        if codetime.active_session(self.connection) is not None:
            return

        cursor = self.connection.execute(
            "INSERT INTO sessions (project, started_at) VALUES (?, ?)",
            (action.project, action.at.isoformat()),
        )
        self.connection.commit()
        self.open_id = cursor.lastrowid

    def _close(self, action, current):
        if self.open_id is None:
            return

        session_id, self.open_id = self.open_id, None
        row = self.connection.execute(
            "SELECT started_at, ended_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        # Already deleted, or closed by 'codetime stop': nothing to do.
        if row is None or row[1] is not None:
            return

        started = datetime.fromisoformat(row[0])
        ended = min(action.at, current)  # never in the future

        if ended <= started:
            self.connection.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
        else:
            self.connection.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (ended.isoformat(), session_id),
            )
        self.connection.commit()
