"""Email outbox: login notices are queued here and sent separately.

Logging in only writes a row to the outbox. A separate step sends the rows,
so a broken email server can never stop someone from logging in.
"""

from datetime import datetime, timezone

from codetime import CodeTimeError

MAX_ATTEMPTS = 3
MAX_ERROR_LENGTH = 200


def ensure_schema(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS email_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            to_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT
        )
        """
    )
    connection.commit()


def queue_login_email(connection, user_id, to_email, login_id, current):
    """Add a login notice to the outbox.

    This does NOT commit, so it saves together with the login itself.
    The same login can only ever produce one row (dedupe_key is unique).
    """
    when = current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = "New login to your CodeTime account"
    body = (
        "Hello,\n\n"
        f"Your CodeTime account was logged in to on {when}.\n\n"
        "If this was you, no action is needed.\n"
        "If it was not you, someone else may know your password. "
        "Change it as soon as you can.\n"
    )

    connection.execute(
        "INSERT OR IGNORE INTO email_outbox "
        "(user_id, to_email, subject, body, dedupe_key, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id,
            to_email,
            subject,
            body,
            f"login:{login_id}",
            current.isoformat(),
        ),
    )


def _describe(error):
    """A short, safe description of a failure. No secrets."""
    if isinstance(error, CodeTimeError):
        text = str(error)  # our own messages are written to be safe
    else:
        text = type(error).__name__
    return text[:MAX_ERROR_LENGTH]


def send_pending(connection, sender, current=None):
    """Try to send every pending email. Returns (sent, failed) for this run.

    sender is a function: sender(to_email, subject, body).
    """
    current = current or datetime.now(timezone.utc)

    rows = connection.execute(
        "SELECT id, to_email, subject, body, attempts "
        "FROM email_outbox WHERE status = 'pending' ORDER BY id"
    ).fetchall()

    sent = 0
    failed = 0

    for row_id, to_email, subject, body, attempts in rows:
        try:
            sender(to_email, subject, body)
        except Exception as error:
            attempts += 1
            status = "failed" if attempts >= MAX_ATTEMPTS else "pending"
            connection.execute(
                "UPDATE email_outbox "
                "SET status = ?, attempts = ?, last_error = ? WHERE id = ?",
                (status, attempts, _describe(error), row_id),
            )
            failed += 1
        else:
            connection.execute(
                "UPDATE email_outbox "
                "SET status = 'sent', attempts = ?, sent_at = ?, "
                "last_error = NULL WHERE id = ?",
                (attempts + 1, current.isoformat(), row_id),
            )
            sent += 1

        connection.commit()

    return sent, failed


def retry_failed(connection):
    """Put emails we gave up on back in the queue. Returns how many."""
    cursor = connection.execute(
        "UPDATE email_outbox SET status = 'pending', attempts = 0 "
        "WHERE status = 'failed'"
    )
    connection.commit()
    return cursor.rowcount


def print_sender(to_email, subject, body):
    """A sender that only prints. Nothing is really sent."""
    print("--- EMAIL (printed, not really sent) ---")
    print(f"To: {to_email}")
    print(f"Subject: {subject}")
    print()
    print(body)