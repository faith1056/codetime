"""Logging in and out.

A login returns a random token. Only a hash of the token is stored, so a
stolen database cannot be used to log in as someone.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import accounts
from codetime import CodeTimeError

TOKEN_LIFETIME = timedelta(days=30)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
GENERIC_ERROR = "Wrong email or password."
LOCKED_ERROR = "Too many failed attempts. Try again later."

# Checked when an email is unknown, so unknown emails take as long as real ones.
_DUMMY_HASH = accounts.hash_password("not-a-real-password")


def _utc_now():
    return datetime.now(timezone.utc)


def ensure_schema(connection):
    accounts.ensure_schema(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS login_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS failed_logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            failed_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _recent_failures(connection, email, current):
    since = (current - FAILURE_WINDOW).isoformat()
    row = connection.execute(
        "SELECT COUNT(*) FROM failed_logins WHERE email = ? AND failed_at >= ?",
        (email, since),
    ).fetchone()
    return row[0]


def login(connection, email, password, current=None):
    """Check the password and return a new login token."""
    current = current or _utc_now()

    try:
        email = accounts.clean_email(email)
    except CodeTimeError:
        raise CodeTimeError(GENERIC_ERROR) from None

    if (
        not isinstance(password, str)
        or len(password) > accounts.MAX_PASSWORD_LENGTH
    ):
        raise CodeTimeError(GENERIC_ERROR)

    if _recent_failures(connection, email, current) >= MAX_FAILURES:
        raise CodeTimeError(LOCKED_ERROR)

    row = connection.execute(
        "SELECT id, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()

    stored = row[1] if row else _DUMMY_HASH
    matches = accounts.verify_password(password, stored)

    if row is None or not matches:
        connection.execute(
            "INSERT INTO failed_logins (email, failed_at) VALUES (?, ?)",
            (email, current.isoformat()),
        )
        connection.commit()
        raise CodeTimeError(GENERIC_ERROR)

    token = secrets.token_urlsafe(32)

    connection.execute("DELETE FROM failed_logins WHERE email = ?", (email,))
    connection.execute(
        "INSERT INTO login_tokens (user_id, token_hash, created_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (
            row[0],
            _hash_token(token),
            current.isoformat(),
            (current + TOKEN_LIFETIME).isoformat(),
        ),
    )
    connection.commit()

    return token


def user_for_token(connection, token, current=None):
    """Return the user id for a valid token, or None."""
    current = current or _utc_now()

    if not isinstance(token, str) or not token:
        return None

    row = connection.execute(
        "SELECT user_id, expires_at, revoked_at FROM login_tokens "
        "WHERE token_hash = ?",
        (_hash_token(token),),
    ).fetchone()

    if row is None:
        return None

    user_id, expires_at, revoked_at = row

    if revoked_at is not None:
        return None

    if datetime.fromisoformat(expires_at) <= current:
        return None

    return user_id


def logout(connection, token, current=None):
    """Cancel a token. Safe to call twice or with a bad token."""
    current = current or _utc_now()

    if not isinstance(token, str) or not token:
        return

    connection.execute(
        "UPDATE login_tokens SET revoked_at = ? "
        "WHERE token_hash = ? AND revoked_at IS NULL",
        (current.isoformat(), _hash_token(token)),
    )
    connection.commit()