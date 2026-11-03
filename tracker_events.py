"""Check the messages the editor extension sends. Nothing else is accepted."""

from datetime import datetime, timedelta

from codetime import CodeTimeError

MAX_PROJECT_LENGTH = 100
MAX_FUTURE = timedelta(minutes=5)
MAX_PAST = timedelta(days=1)


def clean_project(value):
    if not isinstance(value, str):
        raise CodeTimeError("project must be text.")

    name = value.strip()

    if not name or len(name) > MAX_PROJECT_LENGTH:
        raise CodeTimeError(
            f"project must be 1 to {MAX_PROJECT_LENGTH} characters."
        )

    if "/" in name or "\\" in name:
        raise CodeTimeError("project must be a folder name, not a path.")

    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise CodeTimeError("project contains invalid characters.")

    return name


def clean_time(value, current):
    if not isinstance(value, str):
        raise CodeTimeError("time must be text.")

    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise CodeTimeError("time must be an ISO timestamp.") from None

    if moment.tzinfo is not None:
        # The rest of CodeTime uses local time without a time zone.
        moment = moment.astimezone().replace(tzinfo=None)

    if moment > current + MAX_FUTURE:
        raise CodeTimeError("time is too far in the future.")

    if moment < current - MAX_PAST:
        raise CodeTimeError("time is too far in the past.")

    return moment


def parse_event(data, current):
    """Return (project, time) from a message, or raise CodeTimeError."""
    if not isinstance(data, dict):
        raise CodeTimeError("message must be an object.")

    if "project" not in data or "time" not in data:
        raise CodeTimeError("message needs 'project' and 'time'.")

    return clean_project(data["project"]), clean_time(data["time"], current)
