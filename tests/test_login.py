import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import account_login
import accounts
import codetime

GOOD = "correct horse battery"
BAD = "wrong password!!"
T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class TestLogin(unittest.TestCase):
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

    def login(self, email, password=GOOD, at=T0):
        return account_login.login(self.connection, email, password, at)

    def failure_message(self, email, password=BAD, at=T0):
        with self.assertRaises(codetime.CodeTimeError) as caught:
            self.login(email, password, at)
        return str(caught.exception)

    def fail_many(self, email, times, at=T0):
        for _ in range(times):
            self.failure_message(email, BAD, at)

    def test_login_returns_a_long_random_token(self):
        token = self.login("ada@example.com")
        self.assertGreaterEqual(len(token), 40)
        self.assertNotEqual(token, self.login("ada@example.com"))

    def test_only_a_hash_of_the_token_is_stored(self):
        token = self.login("ada@example.com")
        rows = self.connection.execute("SELECT * FROM login_tokens").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertNotIn(token, [str(value) for value in rows[0]])

    def test_token_belongs_to_the_user_who_logged_in(self):
        ada_token = self.login("ada@example.com")
        bob_token = self.login("bob@example.com")
        conn = self.connection
        self.assertEqual(account_login.user_for_token(conn, ada_token, T0), self.ada)
        self.assertEqual(account_login.user_for_token(conn, bob_token, T0), self.bob)

    def test_login_ignores_email_case_and_spaces(self):
        self.assertTrue(self.login("  ADA@Example.com "))

    def test_wrong_password_gets_the_generic_message(self):
        self.assertEqual(
            self.failure_message("ada@example.com"), account_login.GENERIC_ERROR
        )

    def test_unknown_email_gets_the_same_message(self):
        self.assertEqual(
            self.failure_message("ghost@example.com"),
            self.failure_message("ada@example.com"),
        )

    def test_malformed_email_gets_the_same_message(self):
        self.assertEqual(
            self.failure_message("not-an-email"), account_login.GENERIC_ERROR
        )

    def test_huge_password_is_refused_with_the_generic_message(self):
        self.assertEqual(
            self.failure_message("ada@example.com", "x" * 500),
            account_login.GENERIC_ERROR,
        )

    def test_unknown_or_empty_tokens_are_rejected(self):
        conn = self.connection
        self.assertIsNone(account_login.user_for_token(conn, "nope", T0))
        self.assertIsNone(account_login.user_for_token(conn, "", T0))
        self.assertIsNone(account_login.user_for_token(conn, None, T0))

    def test_logout_cancels_the_token(self):
        token = self.login("ada@example.com")
        account_login.logout(self.connection, token, T0)
        self.assertIsNone(account_login.user_for_token(self.connection, token, T0))

    def test_logout_only_cancels_that_one_token(self):
        first = self.login("ada@example.com")
        second = self.login("ada@example.com")
        account_login.logout(self.connection, first, T0)
        self.assertEqual(
            account_login.user_for_token(self.connection, second, T0), self.ada
        )

    def test_logout_twice_or_with_garbage_is_harmless(self):
        token = self.login("ada@example.com")
        account_login.logout(self.connection, token, T0)
        account_login.logout(self.connection, token, T0)
        account_login.logout(self.connection, "garbage", T0)
        account_login.logout(self.connection, None, T0)

    def test_token_expires_after_thirty_days(self):
        token = self.login("ada@example.com")
        conn = self.connection
        inside = T0 + timedelta(days=29)
        outside = T0 + timedelta(days=31)
        self.assertEqual(account_login.user_for_token(conn, token, inside), self.ada)
        self.assertIsNone(account_login.user_for_token(conn, token, outside))

    def test_five_failures_lock_out_even_the_right_password(self):
        self.fail_many("ada@example.com", 5)
        self.assertIn("Too many", self.failure_message("ada@example.com", GOOD))

    def test_lockout_ends_after_the_window(self):
        self.fail_many("ada@example.com", 5)
        later = T0 + timedelta(minutes=16)
        self.assertTrue(self.login("ada@example.com", GOOD, later))

    def test_a_successful_login_clears_earlier_failures(self):
        self.fail_many("ada@example.com", 4)
        self.login("ada@example.com")
        self.fail_many("ada@example.com", 4)
        self.assertTrue(self.login("ada@example.com"))

    def test_lockout_is_per_email(self):
        self.fail_many("ada@example.com", 5)
        self.assertTrue(self.login("bob@example.com"))

    def test_unknown_emails_get_locked_out_too(self):
        self.fail_many("ghost@example.com", 5)
        self.assertIn("Too many", self.failure_message("ghost@example.com"))


if __name__ == "__main__":
    unittest.main()