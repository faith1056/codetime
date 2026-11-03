import os
import stat
import tempfile
import unittest

import codetime
import tracker_auth


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name

    def tearDown(self):
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def test_create_token_saves_a_nonempty_token(self):
        token = tracker_auth.create_token()
        self.assertTrue(len(token) >= 32)
        self.assertEqual(tracker_auth.load_token(), token)

    def test_token_file_is_owner_only(self):
        tracker_auth.create_token()
        mode = stat.S_IMODE(os.stat(tracker_auth.token_path()).st_mode)
        self.assertEqual(mode, 0o600)

    def test_get_or_create_reuses_existing_token(self):
        first = tracker_auth.get_or_create_token()
        second = tracker_auth.get_or_create_token()
        self.assertEqual(first, second)

    def test_correct_token_is_valid(self):
        token = tracker_auth.create_token()
        self.assertTrue(tracker_auth.is_valid(token))

    def test_wrong_token_is_rejected(self):
        tracker_auth.create_token()
        self.assertFalse(tracker_auth.is_valid("wrong"))

    def test_empty_token_is_rejected(self):
        tracker_auth.create_token()
        self.assertFalse(tracker_auth.is_valid(""))

    def test_non_string_token_is_rejected(self):
        tracker_auth.create_token()
        self.assertFalse(tracker_auth.is_valid(None))
        self.assertFalse(tracker_auth.is_valid(123))

    def test_no_saved_token_rejects_everything(self):
        self.assertFalse(tracker_auth.is_valid("anything"))
        self.assertFalse(tracker_auth.is_valid(""))

    def test_empty_token_file_is_treated_as_missing(self):
        tracker_auth.token_path().write_text("")
        self.assertIsNone(tracker_auth.load_token())
        self.assertFalse(tracker_auth.is_valid(""))


if __name__ == "__main__":
    unittest.main()
