import contextlib
import io
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

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

    self.assertEqual(
        account_email.retry_failed(self.connection), 1
    )

    # Retrying must preserve the previous attempt count.
    self.assertEqual(
        self.outbox()[0][4], account_email.MAX_ATTEMPTS
    )

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


    def test_stale_claim_is_recovered(self):
        self.login("ada@example.com")

        row_id = self.connection.execute(
            "SELECT id FROM email_outbox ORDER BY id LIMIT 1"
        ).fetchone()[0]

        stale_time = (
            T0 - timedelta(seconds=account_email.CLAIM_TIMEOUT_SECONDS + 1)
        ).isoformat()

        self.connection.execute(
            """
            UPDATE email_outbox
            SET status = 'sending', claimed_at = ?
            WHERE id = ?
            """,
            (stale_time, row_id),
        )
        self.connection.commit()

        sender = Recorder()
        result = account_email.send_pending(
            self.connection, sender, current=T0
        )

        self.assertEqual(result, (1, 0))
        self.assertEqual(len(sender.sent), 1)
        self.assertEqual(self.outbox()[0][3], "sent")

    def test_concurrent_workers_do_not_send_same_claimed_email(self):
        self.login("ada@example.com")

        first_started = threading.Event()
        release_first = threading.Event()
        first_messages = []
        first_result = []
        first_errors = []

        def blocking_sender(to_email, subject, body):
            first_messages.append((to_email, subject, body))
            first_started.set()
            if not release_first.wait(timeout=5):
                raise TimeoutError("Test sender was not released")

        def run_first_worker():
            connection = codetime.connect()
            try:
                first_result.append(
                    account_email.send_pending(
                        connection, blocking_sender, current=T0
                    )
                )
            except Exception as error:
                first_errors.append(error)
            finally:
                connection.close()

        worker = threading.Thread(target=run_first_worker)
        worker.start()

        try:
            self.assertTrue(
                first_started.wait(timeout=5),
                "The first worker did not begin sending",
            )

            second_sender = Recorder()
            second_result = account_email.send_pending(
                self.connection, second_sender, current=T0
            )

            self.assertEqual(second_result, (0, 0))
            self.assertEqual(second_sender.sent, [])
        finally:
            release_first.set()
            worker.join(timeout=10)

        self.assertFalse(worker.is_alive(), "The first worker did not finish")
        self.assertEqual(first_errors, [])
        self.assertEqual(first_result, [(1, 0)])
        self.assertEqual(len(first_messages), 1)

    def test_email_status_shows_counts_without_changing_queue(self):
        self.login("ada@example.com")
        self.login("bob@example.com")

        with codetime.connect() as connection:
            rows = connection.execute(
                "SELECT id, user_id, to_email, subject, body, created_at "
                "FROM email_outbox ORDER BY id"
            ).fetchall()
            self.assertEqual(len(rows), 2)

            # Keep Ada's message pending and mark Bob's as sending.
            connection.execute(
                "UPDATE email_outbox SET status = 'sending' WHERE id = ?",
                (rows[1][0],),
            )

            # Add two test messages using the real outbox column names.
            for row, status, dedupe_key in (
                (rows[0], "sent", "test-email-status:sent"),
                (rows[1], "failed", "test-email-status:failed"),
            ):
                connection.execute(
                    """
                    INSERT INTO email_outbox
                    (user_id, to_email, subject, body, dedupe_key,
                     status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row[1], row[2], row[3], row[4],
                        dedupe_key, status, row[5],
                    ),
                )

            before = connection.execute(
                "SELECT id, status, attempts, claimed_at "
                "FROM email_outbox ORDER BY id"
            ).fetchall()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            codetime.cmd_email_status(None)

        for expected in (
            "Pending: 1", "Sending: 1", "Sent:    1",
            "Failed:  1", "Total:   4",
        ):
            self.assertIn(expected, output.getvalue())

        with codetime.connect() as connection:
            after = connection.execute(
                "SELECT id, status, attempts, claimed_at "
                "FROM email_outbox ORDER BY id"
            ).fetchall()

        self.assertEqual(before, after)

    def test_email_status_handles_empty_queue(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            codetime.cmd_email_status(None)

        for expected in (
            "Pending: 0", "Sending: 0", "Sent:    0",
            "Failed:  0", "Total:   0",
        ):
            self.assertIn(expected, output.getvalue())

    def test_email_status_is_registered_in_cli(self):
        args = codetime.build_parser().parse_args(["email-status"])
        self.assertEqual(args.command, "email-status")

    def test_print_sender_shows_the_email(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            account_email.print_sender("ada@example.com", "Hi", "Body text")
        output = buffer.getvalue()
        self.assertIn("ada@example.com", output)
        self.assertIn("Body text", output)


if __name__ == "__main__":
    unittest.main()