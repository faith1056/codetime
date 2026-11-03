"""Connects the state machine, the database store, and crash recovery."""

import tracker_store
from tracker_state import DEFAULT_IDLE_LIMIT, State, Tracker


class Engine:
    """Holds tracking state only. Each call is given its own connection."""

    def __init__(self, idle_limit=DEFAULT_IDLE_LIMIT):
        self.idle_limit = idle_limit
        self.tracker = Tracker(idle_limit)
        self.store = tracker_store.Store()

    def start(self, connection, current):
        """Run crash recovery once. Returns None, 'closed' or 'deleted'."""
        return tracker_store.recover(connection, current, self.idle_limit)

    def _apply(self, connection, actions, current):
        self.store.apply(connection, actions, current)
        if self.tracker.state is State.ACTIVE:
            tracker_store.write_last_seen(self.tracker.last_activity)
        else:
            self._clear_last_seen()

    def _clear_last_seen(self):
        try:
            tracker_store.last_seen_path().unlink()
        except OSError:
            pass

    def _notice_manual_stop(self, connection, current):
        """If our row was stopped from outside, go to PAUSED and stay there."""
        if self.tracker.state is State.ACTIVE and (
            self.store.closed_from_outside(connection)
        ):
            self.tracker.pause(current)
            self._clear_last_seen()

    def activity(self, connection, project, current):
        self._notice_manual_stop(connection, current)
        actions = self.tracker.activity(project, current)
        self._apply(connection, actions, current)

    def tick(self, connection, current):
        self._notice_manual_stop(connection, current)
        actions = self.tracker.check_idle(current)
        self._apply(connection, actions, current)

    def pause(self, connection, current):
        self._apply(connection, self.tracker.pause(current), current)

    def resume(self, current):
        self.tracker.resume(current)

    def stop(self, connection, current):
        self._apply(connection, self.tracker.stop(current), current)
