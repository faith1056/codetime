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
except ImportError:  # the web libraries are optional for the CLI tests
    TestClient = None
    create_app = None

LOCAL = "http://127.0.0.1:47625"


@unittest.skipIf(TestClient is None, "FastAPI is not installed.")
class TestLocalApiGuard(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(create_app(), base_url=LOCAL)
        with closing(codetime.connect()) as connection:
            account_login.ensure_schema(connection)
            accounts.register(
                connection,
                "guard-test@example.com",
                "correct horse battery",
            )
            self.account_token = account_login.login(
                connection,
                "guard-test@example.com",
                "correct horse battery",
            )
            self.user_id = account_login.user_for_token(
                connection, self.account_token
            )
        self.headers = {
            "X-CodeTime-Account-Token": self.account_token,
        }

    def tearDown(self):
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def start_manual_session(self):
        with closing(codetime.connect()) as connection:
            codetime.start_session(
                connection, "alpha", user_id=self.user_id
            )

    def session_is_running(self):
        with closing(codetime.connect()) as connection:
            return codetime.active_session(connection) is not None

    def test_unknown_host_is_rejected(self):
        attacker = TestClient(create_app(), base_url="http://evil.example")
        response = attacker.get("/api/status")
        self.assertEqual(response.status_code, 400)

    def test_localhost_name_is_allowed(self):
        client = TestClient(create_app(), base_url="http://localhost:47625")
        self.assertEqual(client.get("/health").status_code, 200)

    def test_cross_origin_stop_is_refused_and_changes_nothing(self):
        self.start_manual_session()
        response = self.client.post(
            "/api/stop",
            headers={**self.headers, "Origin": "http://evil.example"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.session_is_running())

    def test_same_origin_stop_works(self):
        self.start_manual_session()
        response = self.client.post(
            "/api/stop",
            headers={**self.headers, "Origin": LOCAL},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.session_is_running())

    def test_request_without_origin_is_not_blocked_by_this_guard(self):
        # Command-line tools send no Origin. A token (the next step) covers them.
        self.start_manual_session()
        response = self.client.post("/api/stop", headers=self.headers)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()