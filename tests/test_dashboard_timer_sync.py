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
except ImportError:
    TestClient = None
    create_app = None


@unittest.skipIf(TestClient is None, "FastAPI is not installed.")
class TestDashboardTimerSync(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(
            create_app(),
            base_url="http://127.0.0.1",
        )
        with codetime.connect() as connection:
            account_login.ensure_schema(connection)
            accounts.register(
                connection,
                "timer-test@example.com",
                "correct horse battery",
            )
            self.account_token = account_login.login(
                connection,
                "timer-test@example.com",
                "correct horse battery",
            )

        self.headers = {
            "X-CodeTime-Token": tracker_auth.create_token(),
            "X-CodeTime-Account-Token": self.account_token,
        }

    def tearDown(self):
        self.client.close()

        if self.old_home is None:
            os.environ.pop("CODETIME_HOME", None)
        else:
            os.environ["CODETIME_HOME"] = self.old_home

        self.folder.cleanup()

    def event(self, project="alpha"):
        return self.client.post(
            "/tracker/event",
            json={
                "project": project,
                "time": codetime.now().isoformat(),
            },
            headers=self.headers,
        )

    def rows(self):
        with codetime.connect() as connection:
            return connection.execute(
                "SELECT project, started_at, ended_at "
                "FROM sessions ORDER BY id"
            ).fetchall()

    def test_manual_start_pauses_automatic_tracking(self):
        self.event("alpha")

        response = self.client.post(
            "/api/start",
            json={"project": "Study"},
            headers={"X-CodeTime-Account-Token": self.account_token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"], "Study")

        self.event("alpha")

        rows = self.rows()
        open_rows = [row for row in rows if row[2] is None]

        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0][0], "Study")

    def test_manual_stop_allows_automatic_tracking_to_resume(self):
        started = self.client.post(
            "/api/start",
            json={"project": "Study"},
            headers={"X-CodeTime-Account-Token": self.account_token},
        )
        self.assertEqual(started.status_code, 200)

        stopped = self.client.post(
            "/api/stop",
            headers={"X-CodeTime-Account-Token": self.account_token},
        )
        self.assertEqual(stopped.status_code, 200)

        self.event("alpha")

        rows = self.rows()
        open_rows = [row for row in rows if row[2] is None]

        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0][0], "alpha")

    def test_empty_project_is_rejected(self):
        response = self.client.post(
            "/api/start",
            json={"project": "   "},
            headers={"X-CodeTime-Account-Token": self.account_token},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
