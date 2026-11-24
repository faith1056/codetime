"""Account-isolated scheduling for CodeTime email reports.

Reports are opt-in and use local calendar dates. Only complete reporting
periods beginning on or after the latest preference update are eligible.
"""

from datetime import datetime, time, timedelta, timezone

import account_email
import account_login
import codetime


def ensure_schema(connection):
    """Create per-account report preferences."""
    account_login.ensure_schema(connection)
    account_email.ensure_schema(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS report_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 0
                CHECK (enabled IN (0, 1)),
            frequency TEXT NOT NULL DEFAULT 'daily'
                CHECK (frequency IN ('daily', 'weekly')),
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def get_preferences(connection, user_id):
    """Return one account's report preferences and registered email."""
    ensure_schema(connection)

    account = connection.execute(
        "SELECT email FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if account is None:
        raise codetime.CodeTimeError("Account not found.")

    row = connection.execute(
        "SELECT enabled, frequency FROM report_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row is None:
        return {
            "enabled": False,
            "frequency": "daily",
            "email": account[0],
        }

    return {
        "enabled": bool(row[0]),
        "frequency": row[1],
        "email": account[0],
    }


def update_preferences(connection, user_id, enabled, frequency, current=None):
    """Save preferences for one account; the recipient is never user supplied."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false.")

    if frequency not in ("daily", "weekly"):
        raise ValueError("frequency must be daily or weekly.")

    ensure_schema(connection)

    exists = connection.execute(
        "SELECT 1 FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if exists is None:
        raise codetime.CodeTimeError("Account not found.")

    current = _local_naive(current or codetime.now())

    connection.execute(
        """
        INSERT INTO report_preferences
            (user_id, enabled, frequency, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            enabled = excluded.enabled,
            frequency = excluded.frequency,
            updated_at = excluded.updated_at
        """,
        (user_id, int(enabled), frequency, current.isoformat()),
    )
    connection.commit()

    return get_preferences(connection, user_id)


def _local_naive(current):
    """Match CodeTime's local, timezone-naive session timestamps."""
    if current.tzinfo is None:
        return current
    return current.astimezone().replace(tzinfo=None)


def _periods_to_queue(frequency, enabled_at, current):
    """Yield eligible completed periods in chronological order."""
    today_start = datetime.combine(current.date(), time.min)

    if frequency == "daily":
        start = datetime.combine(enabled_at.date(), time.min)

        # Do not include the day in which the user opted in partway through.
        if start < enabled_at:
            start += timedelta(days=1)

        while start + timedelta(days=1) <= today_start:
            end = start + timedelta(days=1)
            yield start, end
            start = end

    elif frequency == "weekly":
        # Weeks run Monday 00:00 through the following Monday 00:00.
        start = datetime.combine(
            enabled_at.date()
            - timedelta(days=enabled_at.weekday()),
            time.min,
        )

        if start < enabled_at:
            start += timedelta(days=7)

        current_week_start = today_start - timedelta(days=current.weekday())

        while start + timedelta(days=7) <= current_week_start:
            end = start + timedelta(days=7)
            yield start, end
            start = end


def queue_due_reports(connection, current=None):
    """Queue all eligible completed periods without duplicate outbox rows."""
    ensure_schema(connection)

    current = _local_naive(current or codetime.now())

    accounts = connection.execute(
        """
        SELECT p.user_id, p.frequency, p.updated_at, u.email
        FROM report_preferences AS p
        JOIN users AS u ON u.id = p.user_id
        WHERE p.enabled = 1
        """
    ).fetchall()

    queued = 0

    for user_id, frequency, updated_at, email in accounts:
        enabled_at = _local_naive(datetime.fromisoformat(updated_at))

        for start, end in _periods_to_queue(
            frequency, enabled_at, current
        ):
            if frequency == "daily":
                label = f"Daily report for {start:%a %d %b %Y}"
            else:
                last_day = end - timedelta(days=1)
                label = (
                    f"Weekly report for {start:%d %b}–"
                    f"{last_day:%d %b %Y}"
                )

            segments = codetime.collect_segments(
                connection,
                start,
                end,
                current,
                user_id=user_id,
            )
            body = codetime.build_report(segments, label)
            subject = (
                f"CodeTime {frequency} report: {label} - "
                f"{codetime.format_duration(codetime.total_seconds(segments))}"
            )
            dedupe_key = (
                f"scheduled-report:{user_id}:{frequency}:"
                f"{start.date().isoformat()}"
            )

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO email_outbox
                    (user_id, to_email, subject, body, dedupe_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    email,
                    subject,
                    body,
                    dedupe_key,
                    current.isoformat(),
                ),
            )
            queued += cursor.rowcount

    connection.commit()
    return queued
