"""User accounts: registering and checking passwords.

Passwords are never stored. We store a salted scrypt hash instead.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timezone

from codetime import CodeTimeError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128  # stops someone from sending a giant password
MAX_EMAIL_LENGTH = 254

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
HASH_BYTES = 32

EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def ensure_schema(connection):
    """Create the users table if it does not exist. Sessions are untouched."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def clean_email(value):
    if not isinstance(value, str):
        raise CodeTimeError("Email must be text.")

    email = value.strip().lower()

    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_SHAPE.match(email):
        raise CodeTimeError("Please enter a valid email address.")

    return email


def check_password_rules(password):
    if not isinstance(password, str):
        raise CodeTimeError("Password must be text.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise CodeTimeError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise CodeTimeError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
        )


def _scramble(password, salt, n, r, p):
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=HASH_BYTES,
    )


def hash_password(password):
    """Return text like 'scrypt$n$r$p$salt$hash'. The password is not in it."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scramble(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    """True only if password matches the stored hash. Never raises."""
    try:
        name, n, r, p, salt_hex, digest_hex = stored.split("$")
        if name != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = _scramble(
            password, bytes.fromhex(salt_hex), int(n), int(r), int(p)
        )
    except (AttributeError, TypeError, ValueError):
        return False

    return hmac.compare_digest(actual, expected)


def register(connection, email, password):
    """Create an account and return its id."""
    email = clean_email(email)
    check_password_rules(password)

    created = datetime.now(timezone.utc).isoformat()

    try:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES (?, ?, ?)",
            (email, hash_password(password), created),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise CodeTimeError("That email is already registered.") from None

    return cursor.lastrowid
