"""Apply tracker Actions to the existing CodeTime sessions table."""

from datetime import datetime

import codetime


class Store:
    """Remembers which row the tracker opened. Holds no connection."""

    def __init__(self):
        self.open_id = None  # the row this tracker opened, if any
        self.user_id = None

    def apply(self, connection, actions, current):
        for action in actions:
            if action.kind == "open":
                self._open(connection, action)
            elif action.kind == "close":
                self._close(connection, action, current)

    def closed_from_outside(self, connection):
        """True if our row was stopped or deleted by someone else.

        When that happens, the store forgets the row.
        """
        if self.open_id is None:
            return False

        row = connection.execute(
            "SELECT ended_at, user_id FROM sessions WHERE id = ?",
            (self.open_id,),
        ).fetchone()

        if (
            row is not None
            and row[0] is None
            and row[1] == self.user_id
        ):
            return False

        self.open_id = None
        return True

    def _open(self, connection, action):
        running = codetime.active_session(
            connection, user_id=self.user_id
        )

        if running is not None:
            session_id, project, started = running
            row = connection.execute(
                "SELECT user_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()

            # Only replace the unassigned generic dashboard session.
            if (
                project == "CodeTime dashboard"
                and row is not None
                and row[0] is None
            ):
                connection.execute(
                    "UPDATE sessions SET ended_at = ? "
                    "WHERE id = ? AND ended_at IS NULL AND user_id IS NULL",
                    (action.at.isoformat(), session_id),
                )
                connection.commit()
            else:
                # Leave all other running sessions untouched.
                return

        cursor = connection.execute(
            "INSERT INTO sessions (project, started_at, user_id) "
            "VALUES (?, ?, ?)",
            (action.project, action.at.isoformat(), self.user_id),
        )
        connection.commit()
        self.open_id = cursor.lastrowid

    def _close(self, connection, action, current):
        if self.open_id is None:
            return

        session_id, self.open_id = self.open_id, None
        row = connection.execute(
            "SELECT started_at, ended_at, user_id "
            "FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        # Never modify a row that belongs to another account.
        if row is None or row[1] is not None or row[2] != self.user_id:
            return

        started = datetime.fromisoformat(row[0])
        ended = min(action.at, current)  # never in the future

        if ended <= started:
            connection.execute(
                "DELETE FROM sessions WHERE id = ? AND user_id IS ?",
                (session_id, self.user_id),
            )
        else:
            connection.execute(
                "UPDATE sessions SET ended_at = ? "
                "WHERE id = ? AND ended_at IS NULL AND user_id IS ?",
                (ended.isoformat(), session_id, self.user_id),
            )
        connection.commit()
def last_seen_path():
    return codetime.app_dir() / "last_seen.txt"


def write_last_seen(at):
    """Save the time of the latest activity. A timestamp only, nothing else."""
    path = last_seen_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(at.isoformat())
    temp.replace(path)  # replace in one step so a crash can't leave half a file


def read_last_seen():
    """Return the saved time, or None if missing or unreadable."""
    try:
        return datetime.fromisoformat(last_seen_path().read_text().strip())
    except (OSError, ValueError):
        return None


def _unowned_active_session(connection):
    """Newest running row that belongs to no account (tracker/legacy rows).

    Recovery must never touch a row owned by an account.
    """
    row = connection.execute(
        "SELECT id, project, started_at FROM sessions "
        "WHERE ended_at IS NULL AND user_id IS NULL "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return row[0], row[1], datetime.fromisoformat(row[2])


def recover(connection, current, idle_limit):
    """Close a row left open by a crash. Return None, 'closed' or 'deleted'.

    A row is only touched if the tracker's last-seen time is older than
    the idle limit AND the row started at or before that time. Anything
    else (such as a manual session) is left alone. The row is closed at
    the last-seen time, never at the current time.
    """
    running = _unowned_active_session(connection)
    last_seen = read_last_seen()

    if running is None or last_seen is None:
        return None

    session_id, _, started = running

    if current - last_seen < idle_limit or started > last_seen:
        return None

    if started == last_seen:
        connection.execute(
            "DELETE FROM sessions "
            "WHERE id = ? AND ended_at IS NULL AND user_id IS NULL",
            (session_id,),
        )
        connection.commit()
        return "deleted"

    connection.execute(
        "UPDATE sessions SET ended_at = ? "
        "WHERE id = ? AND ended_at IS NULL AND user_id IS NULL",
        (last_seen.isoformat(), session_id),
    )
    connection.commit()
    return "closed"

