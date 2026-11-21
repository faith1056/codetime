import os
import tempfile
import unittest

import account_login
import accounts
import codetime
import tracker_auth

try:
    from fastapi.testclient import TestClient
    from webapp.main import create_app
except ImportError:  # the web libraries are optional for CLI tests
    TestClient = None
    create_app = None


@unittest.skipIf(TestClient is None, "FastAPI is not installed.")
class TestTrackerState(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name

        self.client = TestClient(
            create_app(),
            base_url="http://127.0.0.1:47625",
        )

        with codetime.connect() as connection:
            account_login.ensure_schema(connection)
            accounts.register(
                connection,
                "owner@example.com",
                "owner-test-password",
            )
            accounts.register(
                connection,
                "other@example.com",
                "other-test-password",
            )
            self.owner_token = account_login.login(
                connection,
                "owner@example.com",
                "owner-test-password",
            )
            self.other_token = account_login.login(
                connection,
                "other@example.com",
                "other-test-password",
            )

        self.tracker_token = tracker_auth.create_token()

    def tearDown(self):
        self.client.close()
        if self.old_home is None:
            os.environ.pop("CODETIME_HOME", None)
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def headers(self, account_token):
        return {
            "X-CodeTime-Token": self.tracker_token,
            "X-CodeTime-Account-Token": account_token,
        }

    def test_no_token_file_rejects_everything(self):
        os.unlink(tracker_auth.token_path())
        response = self.client.get(
            "/tracker/state",
            headers={"X-CodeTime-Account-Token": self.owner_token},
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_tracker_token_is_rejected(self):
        response = self.client.get(
            "/tracker/state",
            headers={"X-CodeTime-Account-Token": self.owner_token},
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_tracker_token_is_rejected(self):
        response = self.client.get(
            "/tracker/state",
            headers={
                "X-CodeTime-Token": "wrong",
                "X-CodeTime-Account-Token": self.owner_token,
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_account_token_is_rejected(self):
        response = self.client.get(
            "/tracker/state",
            headers={"X-CodeTime-Token": self.tracker_token},
        )
        self.assertEqual(response.status_code, 401)

    def test_correct_tokens_return_state_to_owner(self):
        response = self.client.get(
            "/tracker/state",
            headers=self.headers(self.owner_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"state": "stopped", "project": None},
        )

    def test_another_account_cannot_read_active_project(self):
        event = self.client.post(
            "/tracker/event",
            json={
                "project": "private-owner-project",
                "time": codetime.now().isoformat(),
            },
            headers=self.headers(self.owner_token),
        )
        self.assertEqual(event.status_code, 200)

        owner_response = self.client.get(
            "/tracker/state",
            headers=self.headers(self.owner_token),
        )
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(
            owner_response.json()["project"],
            "private-owner-project",
        )

        other_response = self.client.get(
            "/tracker/state",
            headers=self.headers(self.other_token),
        )
        self.assertEqual(other_response.status_code, 403)
        self.assertNotIn(
            "private-owner-project",
            other_response.text,
        )


if __name__ == "__main__":
    unittest.main()
