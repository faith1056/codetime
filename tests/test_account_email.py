import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timezone

import account_email
import account_login
import accounts
import codetime

GOOD = "correct horse battery"
BAD = "wrong password!!"
T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class Recorder:
    """A fake sender: remembers what it was asked to send."""

    def __init__(self):
        self.sent = []

    def __call__(self, to_email, subject, body):
        self.sent.append((to_email, subject, body))


def broken_sender(to_email, subject, body):
    raise ConnectionError("password=hunter2 server down")


class TestLoginEmail(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.connection = codetime.connect()
        account_login.ensure_schema(self.connection)
        self.ada = accounts.register(self.connection, "ada@example.com", GOOD)
        self.bob = accounts.register(self.connection, "bob@example.com", GOOD)

    def tearDown(self):
        self.connection.close()
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def outbox(self):
        return self.connection.execute(
            "SELECT to_email, subject, body, status, attempts, last_error "
            "FROM email_outbox ORDER BY id"
        ).fetchall()

    def login(self, email):
        return account_login.login(self.connection, email, GOOD, T0)

    def test_login_queues_one_email_for_that_account(self):
        self.login("ada@example.com")
        rows = self.outbox()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "ada@example.com")
        self.assertEqual(rows[0][3], "pending")

    def test_email_goes_only_to_the_account_that_logged_in(self):
        self.login("bob@example.com")
        self.assertEqual([row[0] for row in self.outbox()], ["bob@example.com"])

    def test_failed_login_queues_nothing(self):
        with self.assertRaises(codetime.CodeTimeError):
            account_login.login(self.connection, "ada@example.com", BAD, T0)
        self.assertEqual(self.outbox(), [])

    def test_email_shows_the_time_but_no_password_or_token(self):
        token = self.login("ada@example.com")
        row = self.outbox()[0]
        text = row[1] + row[2]
        self.assertIn("2026-11-13 12:00 UTC", row[2])
        self.assertNotIn(token, text)
        self.assertNotIn(GOOD, text)

    def test_each_login_gets_its_own_email(self):
        self.login("ada@example.com")
        self.login("ada@example.com")
        self.assertEqual(len(self.outbox()), 2)

    def test_queueing_the_same_login_twice_makes_one_row(self):
        for _ in range(2):
            account_email.queue_login_email(
                self.connection, self.ada, "ada@example.com", 99, T0
            )
        self.assertEqual(len(self.outbox()), 1)

    def test_send_pending_sends_and_marks_sent(self):
        self.login("ada@example.com")
        recorder = Recorder()
        result = account_email.send_pending(self.connection, recorder, T0)
        self.assertEqual(result, (1, 0))
        self.assertEqual(len(recorder.sent), 1)
        self.assertEqual(recorder.sent[0][0], "ada@example.com")
        self.assertEqual(self.outbox()[0][3], "sent")

    def test_running_the_sender_twice_sends_once(self):
        self.login("ada@example.com")
        recorder = Recorder()
        account_email.send_pending(self.connection, recorder, T0)
        result = account_email.send_pending(self.connection, recorder, T0)
        self.assertEqual(result, (0, 0))
        self.assertEqual(len(recorder.sent), 1)

    def test_failed_send_is_recorded_and_login_still_works(self):
        token = self.login("ada@example.com")
        result = account_email.send_pending(self.connection, broken_sender, T0)
        self.assertEqual(result, (0, 1))
        row = self.outbox()[0]
        self.assertEqual((row[3], row[4]), ("pending", 1))
        self.assertEqual(row[5], "ConnectionError")
        self.assertNotIn("hunter2", row[5])
        self.assertEqual(
            account_login.user_for_token(self.connection, token, T0), self.ada
        )

    def test_it_gives_up_after_the_maximum_attempts(self):
        self.login("ada@example.com")
        for _ in range(account_email.MAX_ATTEMPTS):
            account_email.send_pending(self.connection, broken_sender, T0)
        row = self.outbox()[0]
        self.assertEqual((row[3], row[4]), ("failed", account_email.MAX_ATTEMPTS))
        recorder = Recorder()
        result = account_email.send_pending(self.connection, recorder, T0)
        self.assertEqual(result, (0, 0))
        self.assertEqual(recorder.sent, [])

    def test_retry_failed_makes_given_up_emails_sendable_again(self):
        self.login("ada@example.com")
        for _ in range(account_email.MAX_ATTEMPTS):
            account_email.send_pending(self.connection, broken_sender, T0)
        self.assertEqual(account_email.retry_failed(self.connection), 1)
        recorder = Recorder()
        result = account_email.send_pending(self.connection, recorder, T0)
        self.assertEqual(result, (1, 0))
        self.assertEqual(self.outbox()[0][3], "sent")

    def test_one_failure_does_not_block_the_others(self):
        self.login("ada@example.com")
        self.login("bob@example.com")
        delivered = []

        def picky(to_email, subject, body):
            if to_email == "ada@example.com":
                raise ConnectionError("down")
            delivered.append(to_email)

        result = account_email.send_pending(self.connection, picky, T0)
        self.assertEqual(result, (1, 1))
        self.assertEqual(delivered, ["bob@example.com"])

    def test_print_sender_shows_the_email(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            account_email.print_sender("ada@example.com", "Hi", "Body text")
        output = buffer.getvalue()
        self.assertIn("ada@example.com", output)
        self.assertIn("Body text", output)


if __name__ == "__main__":
    unittest.main()