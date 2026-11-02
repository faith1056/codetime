"""The tracking state machine for CodeTime.

It has no database and no clock. The caller passes in the time of each
event, and gets back a list of Actions describing what to save.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

DEFAULT_IDLE_LIMIT = timedelta(minutes=5)


class State(Enum):
    STOPPED = "stopped"
    ACTIVE = "active"
    IDLE = "idle"
    PAUSED = "paused"


@dataclass(frozen=True)
class Action:
    """One thing the caller must save: open or close a session row."""

    kind: str  # "open" or "close"
    project: str
    at: datetime


class Tracker:
    def __init__(self, idle_limit=DEFAULT_IDLE_LIMIT):
        self.idle_limit = idle_limit
        self._reset()

    def _reset(self):
        self.state = State.STOPPED
        self.project = None
        self.last_activity = None

    def check_idle(self, at):
        """Move ACTIVE to IDLE if the idle limit has been reached.

        The row is closed at the time of the LAST activity, so the
        idle minutes are never counted as coding time.
        """
        if (
            self.state is State.ACTIVE
            and at - self.last_activity >= self.idle_limit
        ):
            self.state = State.IDLE
            return [Action("close", self.project, self.last_activity)]
        return []

    def activity(self, project, at):
        if self.state is State.PAUSED:
            return []

        # Ignore events that arrive "from the past" (clock went backwards).
        if self.last_activity is not None and at < self.last_activity:
            return []

        actions = self.check_idle(at)

        if self.state is State.ACTIVE:
            if project == self.project:
                self.last_activity = at
                return actions
            actions.append(Action("close", self.project, at))

        actions.append(Action("open", project, at))
        self.state = State.ACTIVE
        self.project = project
        self.last_activity = at
        return actions

    def pause(self, at):
        if self.state in (State.STOPPED, State.PAUSED):
            return []

        actions = self.check_idle(at)
        if self.state is State.ACTIVE:
            actions.append(Action("close", self.project, at))
        self.state = State.PAUSED
        return actions

    def resume(self, at):
        if self.state is State.PAUSED:
            self._reset()
        return []

    def stop(self, at):
        actions = self.check_idle(at)
        if self.state is State.ACTIVE:
            actions.append(Action("close", self.project, at))
        self._reset()
        return actions
