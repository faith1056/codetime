import os
import stat
import tempfile
import unittest
from datetime import datetime
from io import StringIO
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout, redirect_stderr

import codetime


def at(text):
    return datetime.fromisoformat(text)


class CodeTimeTestCase(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

        self.env_patcher = patch.dict(
            os.environ, {"CODETIME_HOME": self.directory.name}
        )
        self.env_patcher.start()

        self.clock = [at("2026-10-31 09:00:00")]
        self.now_patcher = patch.object(
            codetime, "now", side_effect=lambda: self.clock[0]
        )
        self.now_patcher.start()

        self.connection = codetime.connect()

    def tearDown(self):
        self.connection.close()
        self.now_patcher.stop()
        self.env_patcher.stop()
        self.directory.cleanup()

    def set_time(self, text):
        self.clock[0] = at(text)

    def run_cli(self, *argv):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = codetime.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class TestSessions(CodeTimeTestCase):

    def test_start_then_stop_records_duration(self):
        codetime.start_session(self.connection, "campusflow")
        self.set_time("2026-10-31 11:05:00")

        project, started, ended = codetime.stop_session(self.connection)

        self.assertEqual(project, "campusflow")
        self.assertEqual((ended - started).total_seconds(), 2 * 3600 + 5 * 60)

    def test_cannot_start_twice(self):
        codetime.start_session(self.connection, "one")

        with self.assertRaises(codetime.CodeTimeError):
            codetime.start_session(self.connection, "two")

    def test_cannot_stop_without_a_session(self):
        with self.assertRaises(codetime.CodeTimeError):
            codetime.stop_session(self.connection)

    def test_can_start_again_after_stopping(self):
        codetime.start_session(self.connection, "one")
        codetime.stop_session(self.connection)
        codetime.start_session(self.connection, "two")

        self.assertEqual(codetime.active_session(self.connection)[1], "two")


class TestFormatting(unittest.TestCase):

    def test_format_duration(self):
        self.assertEqual(codetime.format_duration(0), "0m")
        self.assertEqual(codetime.format_duration(30), "<1m")
        self.assertEqual(codetime.format_duration(45 * 60), "45m")
        self.assertEqual(codetime.format_duration(3600), "1h 00m")
        self.assertEqual(codetime.format_duration(2 * 3600 + 5 * 60), "2h 05m")

    def test_period_ranges(self):
        current = at("2026-10-31 15:30:00")  # a Saturday

        start, end, _ = codetime.period_range("today", current)
        self.assertEqual((start, end), (at("2026-10-31"), at("2026-11-01")))

        start, end, _ = codetime.period_range("week", current)
        self.assertEqual((start, end), (at("2026-10-26"), at("2026-11-02")))

        start, end, _ = codetime.period_range("month", current)
        self.assertEqual((start, end), (at("2026-10-01"), at("2026-11-01")))

    def test_month_range_in_december(self):
        start, end, _ = codetime.period_range("month", at("2026-12-15 10:00:00"))
        self.assertEqual((start, end), (at("2026-12-01"), at("2027-01-01")))


class TestReports(CodeTimeTestCase):

    def add_session(self, project, started, ended):
        self.connection.execute(
            "INSERT INTO sessions (project, started_at, ended_at) VALUES (?, ?, ?)",
            (project, started, ended),
        )
        self.connection.commit()

    def test_session_crossing_midnight_is_split(self):
        self.add_session("late", "2026-10-30 23:00:00", "2026-10-31 01:00:00")

        today = codetime.collect_segments(
            self.connection, at("2026-10-31"), at("2026-11-01"), self.clock[0]
        )
        yesterday = codetime.collect_segments(
            self.connection, at("2026-10-30"), at("2026-10-31"), self.clock[0]
        )

        self.assertEqual(codetime.total_seconds(today), 3600)
        self.assertEqual(codetime.total_seconds(yesterday), 3600)

    def test_running_session_counts_up_to_now(self):
        codetime.start_session(self.connection, "live")
        self.set_time("2026-10-31 09:30:00")

        segments = codetime.collect_segments(
            self.connection, at("2026-10-31"), at("2026-11-01"), self.clock[0]
        )

        self.assertEqual(codetime.total_seconds(segments), 30 * 60)

    def test_report_totals_and_projects(self):
        self.add_session("alpha", "2026-10-31 08:00:00", "2026-10-31 09:30:00")
        self.add_session("beta", "2026-10-31 10:00:00", "2026-10-31 10:30:00")

        start, end, label = codetime.period_range("today", self.clock[0])
        segments = codetime.collect_segments(self.connection, start, end, self.clock[0])
        report = codetime.build_report(segments, label)

        self.assertIn("Total: 2h 00m across 2 session(s)", report)
        self.assertIn("alpha", report)
        self.assertIn("1h 30m", report)
        self.assertIn("beta", report)

    def test_empty_report(self):
        report = codetime.build_report([], "Today")
        self.assertIn("No coding time recorded", report)


class TestEmail(CodeTimeTestCase):

    CONFIG = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "me@example.com",
        "SMTP_PASSWORD": "secret",
        "EMAIL_TO": "me@example.com",
    }

    def test_send_email_uses_starttls_and_login(self):
        with patch.object(codetime.smtplib, "SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            codetime.send_email("Subject", "Body", self.CONFIG)

        server.starttls.assert_called_once()
        server.login.assert_called_once_with("me@example.com", "secret")
        sent = server.send_message.call_args[0][0]
        self.assertEqual(sent["Subject"], "Subject")
        self.assertEqual(sent["To"], "me@example.com")

    def test_port_465_uses_ssl(self):
        config = dict(self.CONFIG, SMTP_PORT="465")

        with patch.object(codetime.smtplib, "SMTP_SSL") as smtp:
            codetime.send_email("Subject", "Body", config)

        smtp.assert_called_once()

    def test_missing_config_gives_friendly_error(self):
        with self.assertRaises(codetime.CodeTimeError):
            codetime.send_email("Subject", "Body", {})

    def test_bad_login_gives_friendly_error(self):
        with patch.object(codetime.smtplib, "SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            server.login.side_effect = codetime.smtplib.SMTPAuthenticationError(
                535, b"bad"
            )

            with self.assertRaises(codetime.CodeTimeError) as context:
                codetime.send_email("Subject", "Body", self.CONFIG)

        self.assertIn("app password", str(context.exception))

    def test_config_file_is_private_and_round_trips(self):
        codetime.save_config(self.CONFIG)

        mode = stat.S_IMODE(os.stat(codetime.config_path()).st_mode)
        self.assertEqual(mode, 0o600)

        loaded = codetime.load_config()
        self.assertEqual(loaded["SMTP_PASSWORD"], "secret")

    def test_password_with_equals_sign_is_kept(self):
        codetime.save_config(dict(self.CONFIG, SMTP_PASSWORD="ab=cd ef"))
        self.assertEqual(codetime.load_config()["SMTP_PASSWORD"], "ab=cd ef")


class TestCli(CodeTimeTestCase):


    def test_register_command_creates_account(self):
        with patch("builtins.input", return_value="ada@example.com"), \
             patch("codetime.getpass.getpass", side_effect=[
                 "TestPassword123!",
                 "TestPassword123!",
             ]):
            code, out, err = self.run_cli("register")

        self.assertEqual(code, 0)
        self.assertIn("Account registered successfully.", out)
        self.assertEqual(err, "")

    def test_register_command_rejects_mismatched_passwords(self):
        with patch("builtins.input", return_value="ada@example.com"), \
             patch("codetime.getpass.getpass", side_effect=[
                 "TestPassword123!",
                 "DifferentPassword123!",
             ]):
            code, out, err = self.run_cli("register")

        self.assertEqual(code, 1)
        self.assertIn("Passwords do not match.", err)


    def test_login_command_creates_private_token_file(self):
        with patch("builtins.input", return_value="ada@example.com"), \
             patch("codetime.getpass.getpass", side_effect=[
                 "TestPassword123!",
                 "TestPassword123!",
             ]):
            code, _, err = self.run_cli("register")

        self.assertEqual(code, 0)
        self.assertEqual(err, "")

        with patch("builtins.input", return_value="ada@example.com"), \
             patch("codetime.getpass.getpass", return_value="TestPassword123!"):
            code, out, err = self.run_cli("login")

        self.assertEqual(code, 0)
        self.assertIn("Logged in successfully.", out)
        self.assertEqual(err, "")

        path = codetime.token_path()
        self.assertTrue(path.exists())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertTrue(path.read_text(encoding="utf-8").strip())


    def test_full_flow(self):
        code, out, _ = self.run_cli("start", "demo")
        self.assertEqual(code, 0)
        self.assertIn("Started 'demo'", out)

        self.set_time("2026-10-31 10:15:00")
        code, out, _ = self.run_cli("status")
        self.assertIn("1h 15m", out)

        code, out, _ = self.run_cli("stop")
        self.assertEqual(code, 0)
        self.assertIn("1h 15m", out)

        code, out, _ = self.run_cli("report")
        self.assertIn("demo", out)
        self.assertIn("Total: 1h 15m", out)

    def test_errors_return_exit_code_1(self):
        code, _, err = self.run_cli("stop")
        self.assertEqual(code, 1)
        self.assertIn("No session is running", err)

    def test_report_email_without_setup_fails_cleanly(self):
        code, _, err = self.run_cli("report", "--email")
        self.assertEqual(code, 1)
        self.assertIn("codetime setup", err)

    def test_stop_warns_about_forgotten_sessions(self):
        self.run_cli("start", "forgot")
        self.set_time("2026-10-31 23:00:00")
        self.clock[0] = at("2026-11-01 02:00:00")

        _, out, _ = self.run_cli("stop")
        self.assertIn("Warning", out)


class TestStopAt(CodeTimeTestCase):

    def test_stop_at_earlier_today(self):
        codetime.start_session(self.connection, "work")  # 09:00
        self.set_time("2026-10-31 12:00:00")

        _, started, ended = codetime.stop_session(self.connection, "10:30")

        self.assertEqual(ended, at("2026-10-31 10:30:00"))
        self.assertEqual((ended - started).total_seconds(), 90 * 60)

    def test_stop_at_uses_yesterday_when_time_is_in_the_future(self):
        self.set_time("2026-10-30 14:00:00")
        codetime.start_session(self.connection, "forgot")
        self.set_time("2026-10-31 09:00:00")

        _, _, ended = codetime.stop_session(self.connection, "17:30")

        self.assertEqual(ended, at("2026-10-30 17:30:00"))

    def test_stop_at_before_start_is_rejected(self):
        codetime.start_session(self.connection, "work")  # 09:00
        self.set_time("2026-10-31 09:30:00")

        with self.assertRaises(codetime.CodeTimeError):
            codetime.stop_session(self.connection, "10:00")

        self.assertIsNotNone(codetime.active_session(self.connection))

    def test_bad_time_format_is_rejected(self):
        codetime.start_session(self.connection, "work")

        with self.assertRaises(codetime.CodeTimeError):
            codetime.stop_session(self.connection, "5pm")


class TestLogAndDelete(CodeTimeTestCase):

    def test_log_lists_sessions_and_running_one(self):
        codetime.start_session(self.connection, "done")
        self.set_time("2026-10-31 10:00:00")
        codetime.stop_session(self.connection)
        codetime.start_session(self.connection, "live")

        code, out, _ = self.run_cli("log")

        self.assertEqual(code, 0)
        self.assertIn("done", out)
        self.assertIn("live", out)
        self.assertIn("running", out)

    def test_log_when_empty(self):
        _, out, _ = self.run_cli("log")
        self.assertIn("No sessions recorded", out)

    def test_delete_with_yes_removes_session(self):
        codetime.start_session(self.connection, "oops")
        codetime.stop_session(self.connection)

        code, out, _ = self.run_cli("delete", "1", "--yes")

        self.assertEqual(code, 0)
        self.assertEqual(codetime.list_sessions(self.connection, 10), [])

    def test_delete_asks_and_respects_no(self):
        codetime.start_session(self.connection, "keep")
        codetime.stop_session(self.connection)

        with patch("builtins.input", return_value="n"):
            _, out, _ = self.run_cli("delete", "1")

        self.assertIn("Nothing deleted", out)
        self.assertEqual(len(codetime.list_sessions(self.connection, 10)), 1)

    def test_delete_asks_and_accepts_yes(self):
        codetime.start_session(self.connection, "remove")
        codetime.stop_session(self.connection)

        with patch("builtins.input", return_value="y"):
            self.run_cli("delete", "1")

        self.assertEqual(codetime.list_sessions(self.connection, 10), [])

    def test_delete_unknown_id_fails_cleanly(self):
        code, _, err = self.run_cli("delete", "99", "--yes")

        self.assertEqual(code, 1)
        self.assertIn("no session with ID 99", err)


if __name__ == "__main__":
    unittest.main()