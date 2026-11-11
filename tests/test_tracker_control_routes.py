import os
import tempfile
import unittest

import codetime
import tracker_auth

try:
    from fastapi.testclient import TestClient

    from webapp.main import create_app
except ImportError:  # the web libraries are optional for the CLI tests
    TestClient = None
    create_app = None


@unittest.skipIf(TestClient is None, "FastAPI is not installed.")
class TestControlRoutes(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(create_app(), base_url="http://127.0.0.1:47625")
        self.headers = {"X-CodeTime-Token": tracker_auth.create_token()}

    def tearDown(self):
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def event(self, project="alpha"):
        return self.client.post(
            "/tracker/event",
            json={"project": project, "time": codetime.now().isoformat()},
            headers=self.headers,
        )

    def rows(self):
        connection = codetime.connect()
        try:
            return connection.execute(
                "SELECT project, started_at, ended_at FROM sessions "
                "ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

    def test_all_three_reject_a_missing_token(self):
        for name in ("pause", "resume", "stop"):
            response = self.client.post(f"/tracker/{name}")
            self.assertEqual(response.status_code, 401, name)

    def test_pause_closes_row_and_ignores_events(self):
        self.event()
        response = self.client.post("/tracker/pause", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "paused")
        self.event()
        open_rows = [row for row in self.rows() if row[2] is None]
        self.assertEqual(open_rows, [])

    def test_resume_lets_the_next_event_open_a_row(self):
        self.event()
        self.client.post("/tracker/pause", headers=self.headers)
        response = self.client.post("/tracker/resume", headers=self.headers)
        self.assertEqual(response.json()["state"], "stopped")
        self.event()
        open_rows = [row for row in self.rows() if row[2] is None]
        self.assertEqual(len(open_rows), 1)

    def test_stop_closes_the_open_row(self):
        self.event()
        response = self.client.post("/tracker/stop", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "stopped")

    def test_stop_when_nothing_is_running_is_harmless(self):
        response = self.client.post("/tracker/stop", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
