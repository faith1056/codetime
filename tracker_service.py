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
            # The CLI login identifies the account for background tracking.
            # Keep legacy unowned-session tests/recovery working when no CLI
            # login file exists; web events supply their account explicitly.
            if codetime.token_path().exists():
                try:
                    user_id = codetime.require_cli_user_id(connection)
                except codetime.CodeTimeError:
                    # Never turn an invalid login into an unowned tracker.
                    logging.warning(
                        "CodeTime skipped a tracker tick because the "
                        "CLI account login is missing or invalid."
                    )
                    return

                engine.tick(connection, current, user_id=user_id)
            else:
                # Preserve legacy unowned-session tests and recovery.
                engine.tick(connection, current)


async def tick_forever(engine, lock):
    """Check for inactivity repeatedly."""
    while True:
        await asyncio.sleep(TICK_SECONDS)

        try:
            await asyncio.to_thread(tick_once, engine, lock)
        except Exception:
            logging.exception("CodeTime activity check failed")

# Email delivery deliberately runs separately from the 30-second tracking tick.
# A slow retry interval prevents repeated SMTP failures from hammering a server.
EMAIL_DELIVERY_INTERVAL_SECONDS = 900


def deliver_due_emails():
    """Queue scheduled reports and deliver pending emails when SMTP is configured."""
    import account_email
    import report_scheduler

    with closing(codetime.connect()) as connection:
        report_scheduler.ensure_schema(connection)
        report_scheduler.queue_due_reports(connection)

        config = codetime.load_config()
        required = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
        if any(not config.get(key) for key in required):
            # Reports stay safely queued until the account configures SMTP.
            return 0, 0

        def sender(to_email, subject, body):
            codetime.send_email(
                subject,
                body,
                config,
                to_email=to_email,
            )

        # Recover eligible failures from earlier delivery cycles.
        # The outbox enforces the total attempt limit.
        account_email.retry_failed(connection)

        return account_email.send_pending(connection, sender)


async def email_delivery_forever():
    """Deliver queued email immediately, then repeat at the configured interval."""
    while True:
        try:
            sent, failed = await asyncio.to_thread(deliver_due_emails)
            if sent or failed:
                logging.info(
                    "CodeTime email worker: %s sent, %s failed.",
                    sent,
                    failed,
                )
        except Exception:
            logging.exception("CodeTime email delivery cycle failed.")

        await asyncio.sleep(EMAIL_DELIVERY_INTERVAL_SECONDS)
