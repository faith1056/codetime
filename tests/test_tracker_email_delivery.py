import unittest
from unittest.mock import MagicMock, patch

import account_email
import codetime
import tracker_service


class TrackerEmailDeliveryTests(unittest.TestCase):
    @patch("account_email.send_pending", return_value=(1, 0))
    @patch("account_email.retry_failed", return_value=1)
    @patch("codetime.load_config")
    @patch("report_scheduler.queue_due_reports")
    @patch("report_scheduler.ensure_schema")
    @patch("codetime.connect")
    def test_worker_recovers_failures_before_sending_pending_emails(
        self,
        connect,
        ensure_schema,
        queue_reports,
        load_config,
        retry_failed,
        send_pending,
    ):
        connection = MagicMock()
        connect.return_value = connection
        load_config.return_value = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "test-user",
            "SMTP_PASSWORD": "test-password",
        }

        result = tracker_service.deliver_due_emails()

        self.assertEqual(result, (1, 0))
        ensure_schema.assert_called_once_with(connection)
        queue_reports.assert_called_once_with(connection)
        retry_failed.assert_called_once_with(connection)
        send_pending.assert_called_once()

        # The connection is closed even when delivery succeeds.
        connection.close.assert_called_once()

    @patch("account_email.send_pending")
    @patch("account_email.retry_failed")
    @patch("codetime.load_config", return_value={})
    @patch("report_scheduler.queue_due_reports")
    @patch("report_scheduler.ensure_schema")
    @patch("codetime.connect")
    def test_worker_keeps_reports_queued_without_smtp_configuration(
        self,
        connect,
        ensure_schema,
        queue_reports,
        load_config,
        retry_failed,
        send_pending,
    ):
        connection = MagicMock()
        connect.return_value = connection

        result = tracker_service.deliver_due_emails()

        self.assertEqual(result, (0, 0))
        ensure_schema.assert_called_once_with(connection)
        queue_reports.assert_called_once_with(connection)
        retry_failed.assert_not_called()
        send_pending.assert_not_called()
        connection.close.assert_called_once()

    @patch("codetime.send_email")
    @patch("account_email.send_pending")
    @patch("account_email.retry_failed")
    @patch("codetime.load_config")
    @patch("report_scheduler.queue_due_reports")
    @patch("report_scheduler.ensure_schema")
    @patch("codetime.connect")
    def test_worker_sender_uses_the_supplied_account_recipient(
        self,
        connect,
        ensure_schema,
        queue_reports,
        load_config,
        retry_failed,
        send_pending,
        send_email,
    ):
        connection = MagicMock()
        connect.return_value = connection
        config = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "test-user",
            "SMTP_PASSWORD": "test-password",
        }
        load_config.return_value = config

        tracker_service.deliver_due_emails()

        sender = send_pending.call_args.args[1]
        sender(
            "account@example.com",
            "CodeTime daily report",
            "Private report contents",
        )

        send_email.assert_called_once_with(
            "CodeTime daily report",
            "Private report contents",
            config,
            to_email="account@example.com",
        )


if __name__ == "__main__":
    unittest.main()
