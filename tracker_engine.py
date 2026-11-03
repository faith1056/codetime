"""Connects the state machine, the database store, and crash recovery."""

import tracker_store
from tracker_state import DEFAULT_IDLE_LIMIT, State, Tracker


class Engine:
    def __init__(self, connection, idle_limit=DEFAULT_IDLE_LIMIT):
        self.connection = connection
        self.idle_limit = idle_limit
        self.tracker = Tracker(idle_limit)
        self.store = tracker_store.Store(connection)

    def start(self, current):
        """Run crash recovery once. Returns None, 'closed' or 'deleted'."""
        return tracker_store.recover(
            self.connection, current, self.idle_limit
        )

    def _apply(self, actions, current):
        self.store.apply(actions, current)
        if self.tracker.state is State.ACTIVE:
            tracker_store.write_last_seen(self.tracker.last_activity)
        else:
            self._clear_last_seen()

    def _clear_last_seen(self):
        try:
            tracker_store.last_seen_path().unlink()
        except OSError:
            pass

    def activity(self, project, current):
        actions = self.tracker.activity(project, current)
        self._apply(actions, current)

    def tick(self, current):
        actions = self.tracker.check_idle(current)
        self._apply(actions, current)

    def pause(self, current):
        self._apply(self.tracker.pause(current), current)

    def resume(self, current):
        self.tracker.resume(current)

    def stop(self, current):
        self._apply(self.tracker.stop(current), current)
