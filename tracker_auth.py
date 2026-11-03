"""A secret token that protects the local tracking endpoint."""

import hmac
import os
import secrets

import codetime


def token_path():
    return codetime.app_dir() / "token"


def create_token():
    """Make a new random token and save it so only the owner can read it."""
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)

    # Create the file with owner-only permissions from the start.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    return token


def load_token():
    """Return the saved token, or None if it is missing or empty."""
    try:
        token = token_path().read_text().strip()
    except OSError:
        return None
    return token or None


def get_or_create_token():
    return load_token() or create_token()


def is_valid(candidate):
    """True only if candidate matches the saved token exactly."""
    saved = load_token()
    if saved is None or not isinstance(candidate, str):
        return False
    return hmac.compare_digest(
        candidate.encode("utf-8"), saved.encode("utf-8")
    )
