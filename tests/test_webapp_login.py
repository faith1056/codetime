import os
import tempfile
import unittest
from contextlib import closing

import accounts
import account_login
import codetime

try:
    from fastapi.testclient import TestClient
    from webapp.main import create_app
except ImportError:
    TestClient = None
    create_app = None

PASSWORD = "test-account-password"


@unittest.skipIf(TestClient is None, "FastAPI is not installed.")
class WebLoginTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(
            create_app(), base_url="http://127.0.0.1:47625"
        )
        with closing(codetime.connect()) as connection:
            account_login.ensure_schema(connection)
            accounts.register(connection, "a@example.com", PASSWORD)

    def tearDown(self):
        self.client.close()
        if self.old_home is None:
            os.environ.pop("CODETIME_HOME", None)
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def login(self, email="a@example.com", password=PASSWORD):
        return self.client.post(
            "/api/login", json={"email": email, "password": password}
        )

    def test_login_returns_working_token(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        status = self.client.get(
            "/api/status", headers={"X-CodeTime-Account-Token": token}
        )
        self.assertEqual(status.status_code, 200)

    def test_wrong_password_and_unknown_email_look_the_same(self):
        wrong = self.login(password="not-the-password")
        unknown = self.login(email="nobody@example.com")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertNotIn("token", wrong.json())

    def test_missing_fields_are_rejected(self):
        response = self.client.post("/api/login", json={"email": "a@example.com"})
        self.assertEqual(response.status_code, 422)

    def test_repeated_failures_lock_out(self):
        for _ in range(account_login.MAX_FAILURES):
            self.login(password="not-the-password")
        self.assertEqual(self.login().status_code, 429)

    def test_logout_revokes_token(self):
        token = self.login().json()["token"]
        headers = {"X-CodeTime-Account-Token": token}
        self.assertEqual(
            self.client.post("/api/logout", headers=headers).status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/status", headers=headers).status_code, 401
        )

    def test_logout_without_token_is_harmless(self):
        self.assertEqual(self.client.post("/api/logout").status_code, 200)


if __name__ == "__main__":
    unittest.main()
