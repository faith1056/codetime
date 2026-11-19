"""Startup work and periodic system-activity checks for CodeTime."""

import asyncio
import logging
import math
from contextlib import closing
from datetime import timedelta

import codetime
import codetime_activity
import tracker_auth

from tracker_state import State


TICK_SECONDS = 30


def startup(engine, lock, current=None):
    """Create the token and recover from a crash."""
    tracker_auth.get_or_create_token()

    if current is None:
        current = codetime.now()

    with lock:
        with closing(codetime.connect()) as connection:
            return engine.start(connection, current)


def _read_idle_seconds(activity_provider):
    """Read a valid idle-time value, or return None if unavailable."""
    try:
        idle_seconds = activity_provider()
    except Exception:
        logging.exception("CodeTime could not read system idle time")
        return None

    if idle_seconds is None:
        return None

    if isinstance(idle_seconds, bool):
        return None

    if not isinstance(idle_seconds, (int, float)):
        return None

    if not math.isfinite(idle_seconds) or idle_seconds < 0:
        return None

    return idle_seconds


def tick_once(engine, lock, current=None, activity_provider=None):
    """Check system activity and update the tracking state."""
    # An explicit time is used by tests and simulated-time callers.
    # Those calls must not consult the real computer's activity.
    use_system_activity = current is None

    if current is None:
        current = codetime.now()

    # Allow tests to provide their own activity detector.
    if activity_provider is None:
        activity_provider = codetime_activity.get_idle_seconds

    idle_seconds = (
        _read_idle_seconds(activity_provider)
        if use_system_activity
        else None
    )

    with lock:
        if (
            engine.tracker.state is State.ACTIVE
            and idle_seconds is not None
        ):
            last_system_activity = current - timedelta(
                seconds=idle_seconds
            )

            previous_activity = engine.tracker.last_activity

            if (
                previous_activity is None
                or last_system_activity > previous_activity
            ):
                engine.tracker.last_activity = last_system_activity

        with closing(codetime.connect()) as connection:
            engine.tick(connection, current)


async def tick_forever(engine, lock):
    """Check for inactivity repeatedly."""
    while True:
        await asyncio.sleep(TICK_SECONDS)

        try:
            await asyncio.to_thread(tick_once, engine, lock)
        except Exception:
            logging.exception("CodeTime activity check failed")