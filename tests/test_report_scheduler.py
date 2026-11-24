import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import account_login
import accounts
import codetime
import report_scheduler


class ReportSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env_patcher = patch.dict(
            os.environ, {"CODETIME_HOME": self.directory.name}
        )
        self.env_patcher.start()

        self.connection = codetime.connect()
        account_login.ensure_schema(self.connection)
        report_scheduler.ensure_schema(self.connection)

        accounts.register(
            self.connection, "first@example.com", "FirstPassword123!"
        )
        accounts.register(
            self.connection, "second@example.com", "SecondPassword123!"
        )

        self.first_id = self.connection.execute(
            "SELECT id FROM users WHERE email = ?",
            ("first@example.com",),
        ).fetchone()[0]
        self.second_id = self.connection.execute(
            "SELECT id FROM users WHERE email = ?",
            ("second@example.com",),
        ).fetchone()[0]

    def tearDown(self):
        self.connection.close()
        self.env_patcher.stop()
        self.directory.cleanup()

    def test_daily_report_is_opt_in_and_deduplicated(self):
        preferences = report_scheduler.get_preferences(
            self.connection, self.first_id
        )
        self.assertFalse(preferences["enabled"])
        self.assertEqual(preferences["email"], "first@example.com")

        report_scheduler.update_preferences(
            self.connection,
            self.first_id,
            True,
            "daily",
            current=datetime(2026, 11, 23, 0, 0),
        )

        current = datetime(2026, 11, 26, 12, 0)
        self.assertEqual(
            report_scheduler.queue_due_reports(self.connection, current), 3
        )
        self.assertEqual(
            report_scheduler.queue_due_reports(self.connection, current), 0
        )

        rows = self.connection.execute(
            """
            SELECT user_id, to_email, dedupe_key, created_at
            FROM email_outbox
            WHERE dedupe_key LIKE 'scheduled-report:%'
            ORDER BY dedupe_key
            """
        ).fetchall()

        self.assertEqual(len(rows), 3)
        self.assertTrue(
            all(row[0] == self.first_id for row in rows)
        )
        self.assertTrue(
            all(row[1] == "first@example.com" for row in rows)
        )
        self.assertEqual(
            {row[2] for row in rows},
            {
                f"scheduled-report:{self.first_id}:daily:2026-11-23",
                f"scheduled-report:{self.first_id}:daily:2026-11-24",
                f"scheduled-report:{self.first_id}:daily:2026-11-25",
            },
        )
        self.assertTrue(
            all(row[3] == "2026-11-26T12:00:00" for row in rows)
        )
    def test_disabled_account_does_not_receive_a_report(self):
        report_scheduler.update_preferences(
            self.connection,
            self.first_id,
            True,
            "daily",
            current=datetime(2026, 11, 23, 0, 0),
        )

        self.assertEqual(
            report_scheduler.queue_due_reports(
                self.connection, datetime(2026, 11, 24, 12, 0)
            ),
            1,
        )

        recipients = self.connection.execute(
            """
            SELECT to_email FROM email_outbox
            WHERE dedupe_key LIKE 'scheduled-report:%'
            """
        ).fetchall()
        self.assertEqual(recipients, [("first@example.com",)])
    def test_weekly_report_catches_up_after_monday(self):
        report_scheduler.update_preferences(
            self.connection,
            self.first_id,
            True,
            "weekly",
            current=datetime(2026, 11, 9, 0, 0),
        )

        current = datetime(2026, 11, 24, 12, 0)
        self.assertEqual(
            report_scheduler.queue_due_reports(self.connection, current), 2
        )
        self.assertEqual(
            report_scheduler.queue_due_reports(self.connection, current), 0
        )

        rows = self.connection.execute(
            """
            SELECT to_email, dedupe_key, subject
            FROM email_outbox
            WHERE dedupe_key LIKE 'scheduled-report:%'
            ORDER BY dedupe_key
            """
        ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertTrue(
            all(row[0] == "first@example.com" for row in rows)
        )
        self.assertEqual(
            {row[1] for row in rows},
            {
                f"scheduled-report:{self.first_id}:weekly:2026-11-09",
                f"scheduled-report:{self.first_id}:weekly:2026-11-16",
            },
        )
        self.assertTrue(
            all("Weekly report" in row[2] for row in rows)
        )
    def test_manual_email_report_uses_registered_account_email(self):
        with patch.object(codetime, "load_config", return_value={}), patch.object(
            codetime, "send_email"
        ) as send:
            codetime.email_report(
                self.connection, "today", self.first_id
            )

        self.assertEqual(
            send.call_args.kwargs["to_email"], "first@example.com"
        )

    def test_cli_report_email_uses_registered_account_email(self):
        args = SimpleNamespace(period="today", email=True)

        with patch.object(
            codetime, "require_cli_user_id", return_value=self.first_id
        ), patch.object(codetime, "load_config", return_value={}), patch.object(
            codetime, "send_email"
        ) as send:
            codetime.cmd_report(args)

        self.assertEqual(
            send.call_args.kwargs["to_email"], "first@example.com"
        )


if __name__ == "__main__":
    unittest.main()
