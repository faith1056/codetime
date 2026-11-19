import os
import tempfile
import unittest
from contextlib import closing

import account_login
import accounts
import codetime

try:
    from fastapi.testclient import TestClient

    from webapp.main import create_app
except ImportError:
    TestClient = None
    create_app = None


@unittest.skipIf(
    TestClient is None,
    "FastAPI is not installed. Run: pip install -r requirements-dev.txt",
)
class TestDashboardAuthentication(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(
            create_app(),
            base_url="http://127.0.0.1:47625",
        )

    def tearDown(self):
        self.client.close()
        if self.old_home is None:
            os.environ.pop("CODETIME_HOME", None)
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def create_account(self, email):
        with closing(codetime.connect()) as connection:
            account_login.ensure_schema(connection)
            accounts.register(
                connection,
                email,
                "test-account-password",
            )
            token = account_login.login(
                connection,
                email,
                "test-account-password",
            )
        return {"X-CodeTime-Account-Token": token}

    def test_account_cannot_see_another_accounts_sessions(self):
        account_a = self.create_account("account-a@example.com")
        account_b = self.create_account("account-b@example.com")

        with closing(codetime.connect()) as connection:
            user_id = account_login.user_for_token(
                connection,
                account_a["X-CodeTime-Account-Token"],
            )
            codetime.start_session(
                connection,
                "Account A private project",
                user_id=user_id,
            )

        response_a = self.client.get(
            "/api/sessions",
            headers=account_a,
        )
        response_b = self.client.get(
            "/api/sessions",
            headers=account_b,
        )

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertIn(
            "Account A private project",
            str(response_a.json()),
        )
        self.assertNotIn(
            "Account A private project",
            str(response_b.json()),
        )

    def test_account_cannot_stop_another_accounts_session(self):
        account_a = self.create_account("owner@example.com")
        account_b = self.create_account("other@example.com")

        with closing(codetime.connect()) as connection:
            user_id = account_login.user_for_token(
                connection,
                account_a["X-CodeTime-Account-Token"],
            )
            codetime.start_session(
                connection,
                "Owner private project",
                user_id=user_id,
            )

        response_b = self.client.post(
            "/api/stop",
            headers=account_b,
        )
        self.assertEqual(response_b.status_code, 400)

        response_a = self.client.get(
            "/api/sessions",
            headers=account_a,
        )
        self.assertIn("Owner private project", str(response_a.json()))

        stop_response = self.client.post(
            "/api/stop",
            headers=account_a,
        )
        self.assertEqual(stop_response.status_code, 200)

    def test_account_can_view_its_own_sessions(self):
        account_a = self.create_account("my-session@example.com")

        with closing(codetime.connect()) as connection:
            user_id = account_login.user_for_token(
                connection,
                account_a["X-CodeTime-Account-Token"],
            )
            codetime.start_session(
                connection,
                "My own project",
                user_id=user_id,
            )

        response = self.client.get(
            "/api/sessions",
            headers=account_a,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("My own project", str(response.json()))


    def test_health_remains_public(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_session_status_requires_login(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 401)

    def test_recent_sessions_requires_login(self):
        response = self.client.get("/api/sessions")
        self.assertEqual(response.status_code, 401)

    def test_start_session_requires_login(self):
        response = self.client.post(
            "/api/start",
            json={"project": "Private project"},
        )
        self.assertEqual(response.status_code, 401)

    def test_stop_session_requires_login(self):
        response = self.client.post("/api/stop")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()