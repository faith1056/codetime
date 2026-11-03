"""Startup work and the periodic idle check for the tracker."""

import asyncio
import logging
from contextlib import closing

import codetime
import tracker_auth

TICK_SECONDS = 30


def startup(engine, lock, current=None):
    """Create the token and recover from a crash. Returns the recovery result."""
    tracker_auth.get_or_create_token()
    with lock:
        with closing(codetime.connect()) as connection:
            return engine.start(connection, current or codetime.now())


def tick_once(engine, lock, current=None):
    """Check once whether the tracker has gone idle."""
    with lock:
        with closing(codetime.connect()) as connection:
            engine.tick(connection, current or codetime.now())


async def tick_forever(engine, lock):
    """Call tick_once every TICK_SECONDS. Not unit-tested: it uses real time."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await asyncio.to_thread(tick_once, engine, lock)
        except Exception:
            logging.exception("CodeTime idle check failed")
