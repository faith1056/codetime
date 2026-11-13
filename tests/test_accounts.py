import os
import tempfile
import unittest

import accounts
import codetime

GOOD_PASSWORD = "correct horse battery"


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.connection = codetime.connect()
        accounts.ensure_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def stored_users(self):
        return self.connection.execute(
            "SELECT email, password_hash FROM users ORDER BY id"
        ).fetchall()

    def test_register_creates_a_user_with_a_clean_email(self):
        user_id = accounts.register(
            self.connection, "  Ada@Example.com ", GOOD_PASSWORD
        )
        self.assertIsInstance(user_id, int)
        self.assertEqual(self.stored_users()[0][0], "ada@example.com")

    def test_password_is_never_stored_as_plain_text(self):
        accounts.register(self.connection, "ada@example.com", GOOD_PASSWORD)
        self.assertNotIn(GOOD_PASSWORD, self.stored_users()[0][1])

    def test_same_password_gets_a_different_hash_each_time(self):
        accounts.register(self.connection, "ada@example.com", GOOD_PASSWORD)
        accounts.register(self.connection, "bob@example.com", GOOD_PASSWORD)
        first, second = [row[1] for row in self.stored_users()]
        self.assertNotEqual(first, second)

    def test_verify_accepts_the_right_password_only(self):
        accounts.register(self.connection, "ada@example.com", GOOD_PASSWORD)
        stored = self.stored_users()[0][1]
        self.assertTrue(accounts.verify_password(GOOD_PASSWORD, stored))
        self.assertFalse(accounts.verify_password("wrong password!!", stored))

    def test_verify_rejects_garbage_without_crashing(self):
        self.assertFalse(accounts.verify_password(GOOD_PASSWORD, "garbage"))
        self.assertFalse(accounts.verify_password(GOOD_PASSWORD, ""))

    def test_duplicate_email_is_refused_even_with_different_case(self):
        accounts.register(self.connection, "ada@example.com", GOOD_PASSWORD)
        with self.assertRaises(codetime.CodeTimeError):
            accounts.register(self.connection, "ADA@example.com", GOOD_PASSWORD)
        self.assertEqual(len(self.stored_users()), 1)

    def test_short_password_is_refused(self):
        with self.assertRaises(codetime.CodeTimeError):
            accounts.register(self.connection, "ada@example.com", "short")
        self.assertEqual(self.stored_users(), [])

    def test_huge_password_is_refused(self):
        with self.assertRaises(codetime.CodeTimeError):
            accounts.register(self.connection, "ada@example.com", "x" * 500)
        self.assertEqual(self.stored_users(), [])

    def test_bad_emails_are_refused(self):
        for email in ("not-an-email", "a b@example.com", "@example.com", ""):
            with self.assertRaises(codetime.CodeTimeError, msg=email):
                accounts.register(self.connection, email, GOOD_PASSWORD)
        self.assertEqual(self.stored_users(), [])

    def test_the_sessions_table_is_untouched(self):
        columns = [
            row[1]
            for row in self.connection.execute("PRAGMA table_info(sessions)")
        ]
        self.assertEqual(columns, ["id", "project", "started_at", "ended_at"])


if __name__ == "__main__":
    unittest.main()