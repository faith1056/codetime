#!/usr/bin/env python3
"""codetime - track how long you code and email yourself a report.

Usage:
    codetime setup                 one-time email setup
    codetime start [project]       start the timer (project defaults to the folder name)
    codetime status                show the running session
    codetime stop [--email]        stop the timer
    codetime report [period]       today (default), week, month, or all
                    [--email]      also send the report to your inbox
"""

import argparse
import getpass
import os
import smtplib
import sqlite3
import ssl
import sys
from collections import defaultdict
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from pathlib import Path

PERIODS = ("today", "week", "month", "all")
STALE_SESSION_HOURS = 12
CONFIG_KEYS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_TO",
)


class CodeTimeError(Exception):
    """A problem the user can fix. Shown without a traceback."""


# ---------------------------------------------------------------------------
# Time and formatting helpers
# ---------------------------------------------------------------------------

def now():
    """Current local time, without microseconds. Tests replace this."""
    return datetime.now().replace(microsecond=0)


def format_duration(seconds):
    """Turn seconds into text like '2h 05m', '45m', or '<1m'."""
    minutes = int(seconds // 60)

    if minutes < 1:
        return "<1m" if seconds > 0 else "0m"

    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"

    return f"{minutes}m"


def period_range(period, current):
    """Return (start, end, label) for today, week, month, or all."""
    today = datetime.combine(current.date(), time.min)

    if period == "today":
        return (
            today,
            today + timedelta(days=1),
            f"Today, {today:%a %d %b %Y}",
        )

    if period == "week":
        start = today - timedelta(days=today.weekday())
        return (
            start,
            start + timedelta(days=7),
            f"Week of {start:%a %d %b %Y}",
        )

    if period == "month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end, f"{start:%B %Y}"

    if period == "all":
        return datetime.min, datetime.max, "All time"

    raise CodeTimeError(f"Unknown period: {period}")


# ---------------------------------------------------------------------------
# Storage (SQLite in ~/.codetime)
# ---------------------------------------------------------------------------

def app_dir():
    custom = os.environ.get("CODETIME_HOME")
    return Path(custom) if custom else Path.home() / ".codetime"


def connect():
    directory = app_dir()
    directory.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(directory / "sessions.db")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT
        )
        """
    )
    return connection


def active_session(connection):
    """Return (id, project, started_at) for the running session, or None."""
    row = connection.execute(
        "SELECT id, project, started_at FROM sessions "
        "WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if row is None:
        return None

    return row[0], row[1], datetime.fromisoformat(row[2])


def start_session(connection, project):
    running = active_session(connection)

    if running:
        raise CodeTimeError(
            f"'{running[1]}' has been running since "
            f"{running[2]:%a %d %b %H:%M}. Run 'codetime stop' first."
        )

    started = now()

    connection.execute(
        "INSERT INTO sessions (project, started_at) VALUES (?, ?)",
        (project, started.isoformat()),
    )
    connection.commit()

    return started


def stop_session(connection):
    running = active_session(connection)

    if running is None:
        raise CodeTimeError("No session is running. Start one with 'codetime start'.")

    session_id, project, started = running
    ended = max(now(), started)

    connection.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (ended.isoformat(), session_id),
    )
    connection.commit()

    return project, started, ended


def collect_segments(connection, start, end, current):
    """Return (session_id, project, day, seconds) pieces inside [start, end).

    Sessions that cross midnight are split so each day gets its own time.
    A running session counts up to the current moment.
    """
    rows = connection.execute(
        "SELECT id, project, started_at, ended_at FROM sessions"
    ).fetchall()

    segments = []

    for session_id, project, started_text, ended_text in rows:
        session_start = datetime.fromisoformat(started_text)
        session_end = (
            datetime.fromisoformat(ended_text) if ended_text else current
        )

        cursor = max(session_start, start)
        limit = min(session_end, end)

        while cursor < limit:
            midnight = datetime.combine(
                cursor.date() + timedelta(days=1), time.min
            )
            piece_end = min(midnight, limit)

            segments.append(
                (
                    session_id,
                    project,
                    cursor.date(),
                    (piece_end - cursor).total_seconds(),
                )
            )
            cursor = piece_end

    return segments


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def total_seconds(segments):
    return sum(segment[3] for segment in segments)


def build_report(segments, label):
    total = total_seconds(segments)
    sessions = len({segment[0] for segment in segments})

    lines = [f"Code time report: {label}", ""]

    if not segments:
        lines.append("No coding time recorded for this period.")
        return "\n".join(lines)

    lines.append(f"Total: {format_duration(total)} across {sessions} session(s)")

    by_project = defaultdict(float)
    by_day = defaultdict(float)

    for _, project, day, seconds in segments:
        by_project[project] += seconds
        by_day[day] += seconds

    width = max(len(name) for name in by_project)

    lines += ["", "By project:"]
    for name, seconds in sorted(by_project.items(), key=lambda item: -item[1]):
        lines.append(f"  {name:<{width}}  {format_duration(seconds)}")

    lines += ["", "By day:"]
    for day, seconds in sorted(by_day.items()):
        lines.append(f"  {day:%a %d %b}  {format_duration(seconds)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def config_path():
    return app_dir() / "config.env"


def load_config():
    """Read config.env. Environment variables named CODETIME_<KEY> override it."""
    config = {}
    path = config_path()

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

    for key in CONFIG_KEYS:
        override = os.environ.get(f"CODETIME_{key}")
        if override:
            config[key] = override

    return config


def save_config(config):
    directory = app_dir()
    directory.mkdir(parents=True, exist_ok=True)

    path = config_path()
    text = "".join(f"{key}={config[key]}\n" for key in CONFIG_KEYS if key in config)

    # Only the owner may read this file because it holds your password.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)

    os.chmod(path, 0o600)


def send_email(subject, body, config):
    missing = [
        key
        for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO")
        if not config.get(key)
    ]

    if missing:
        raise CodeTimeError(
            "Email is not set up yet. Run 'codetime setup' first."
        )

    host = config["SMTP_HOST"]

    try:
        port = int(config.get("SMTP_PORT") or 587)
    except ValueError:
        raise CodeTimeError("SMTP_PORT must be a number.") from None

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.get("EMAIL_FROM") or config["SMTP_USER"]
    message["To"] = config["EMAIL_TO"]
    message.set_content(body)

    context = ssl.create_default_context()

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
                server.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls(context=context)
                server.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
                server.send_message(message)

    except smtplib.SMTPAuthenticationError:
        raise CodeTimeError(
            "The email server rejected your login. For Gmail, use an app "
            "password, not your normal password. Run 'codetime setup' to retry."
        ) from None

    except (smtplib.SMTPException, OSError) as error:
        raise CodeTimeError(f"Could not send the email: {error}") from None


def email_report(connection, period):
    start, end, label = period_range(period, now())
    segments = collect_segments(connection, start, end, now())
    report = build_report(segments, label)

    subject = f"Code time report: {label} - {format_duration(total_seconds(segments))}"
    send_email(subject, report, load_config())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default or ""


def cmd_setup(args):
    print("Email setup. Your answers are saved in", config_path())
    print("For Gmail: turn on 2-step verification, then create an app password")
    print("at https://myaccount.google.com/apppasswords\n")

    config = {
        "SMTP_HOST": ask("SMTP server", "smtp.gmail.com"),
        "SMTP_PORT": ask("SMTP port", "587"),
        "SMTP_USER": ask("Your email address (login)"),
    }
    config["SMTP_PASSWORD"] = getpass.getpass("App password (hidden): ").strip()
    config["EMAIL_TO"] = ask("Send reports to", config["SMTP_USER"])

    for key, value in config.items():
        if not value or "\n" in value:
            raise CodeTimeError(f"{key} cannot be empty.")

    save_config(config)
    print("\nSaved. Test it with: codetime report --email")


def cmd_start(args):
    project = args.project or Path.cwd().name

    with connect() as connection:
        started = start_session(connection, project)

    print(f"Started '{project}' at {started:%H:%M}. Happy coding.")


def cmd_status(args):
    with connect() as connection:
        running = active_session(connection)
        current = now()

        start, end, _ = period_range("today", current)
        today_total = total_seconds(collect_segments(connection, start, end, current))

    if running is None:
        print("No session is running.")
    else:
        _, project, started = running
        elapsed = (current - started).total_seconds()
        print(
            f"Running: '{project}' for {format_duration(elapsed)} "
            f"(since {started:%H:%M})"
        )

    print(f"Today so far: {format_duration(today_total)}")


def cmd_stop(args):
    with connect() as connection:
        project, started, ended = stop_session(connection)
        duration = (ended - started).total_seconds()

        print(f"Stopped '{project}'. This session: {format_duration(duration)}.")

        if duration > STALE_SESSION_HOURS * 3600:
            print(
                f"Warning: that session ran for over {STALE_SESSION_HOURS} hours. "
                "If you forgot to stop it, your totals will be too high."
            )

        if args.email:
            try:
                email_report(connection, "today")
            except CodeTimeError as error:
                print("Your session was saved, but the report was not sent.")
                raise error

            print("Today's report was emailed.")


def cmd_report(args):
    with connect() as connection:
        current = now()
        start, end, label = period_range(args.period, current)
        segments = collect_segments(connection, start, end, current)
        report = build_report(segments, label)

        print(report)

        if args.email:
            subject = (
                f"Code time report: {label} - "
                f"{format_duration(total_seconds(segments))}"
            )
            send_email(subject, report, load_config())
            print("\nReport emailed.")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="codetime",
        description="Track your coding time and email yourself a report.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("setup", help="set up email (one time)")

    start = commands.add_parser("start", help="start the timer")
    start.add_argument(
        "project", nargs="?", help="project name (default: current folder name)"
    )

    commands.add_parser("status", help="show the running session")

    stop = commands.add_parser("stop", help="stop the timer")
    stop.add_argument(
        "--email", action="store_true", help="email today's report after stopping"
    )

    report = commands.add_parser("report", help="show a report")
    report.add_argument("period", nargs="?", default="today", choices=PERIODS)
    report.add_argument("--email", action="store_true", help="also email the report")

    return parser


HANDLERS = {
    "setup": cmd_setup,
    "start": cmd_start,
    "status": cmd_status,
    "stop": cmd_stop,
    "report": cmd_report,
}


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        HANDLERS[args.command](args)
    except CodeTimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
