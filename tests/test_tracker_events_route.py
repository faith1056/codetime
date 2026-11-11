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
class TestEventRoute(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(create_app(), base_url="http://127.0.0.1:47625")
        self.token = tracker_auth.create_token()
        self.headers = {"X-CodeTime-Token": self.token}

    def tearDown(self):
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def post(self, body, headers=None):
        return self.client.post(
            "/tracker/event",
            json=body,
            headers=self.headers if headers is None else headers,
        )

    def rows(self):
        connection = codetime.connect()
        try:
            return connection.execute(
                "SELECT project, ended_at FROM sessions ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

    def test_missing_token_is_rejected(self):
        response = self.post(
            {"project": "alpha", "time": codetime.now().isoformat()},
            headers={},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.rows(), [])

    def test_good_event_opens_a_session(self):
        response = self.post(
            {"project": "alpha", "time": codetime.now().isoformat()}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"state": "active", "project": "alpha"}
        )
        self.assertEqual(self.rows(), [("alpha", None)])

    def test_two_events_make_one_row(self):
        body = {"project": "alpha", "time": codetime.now().isoformat()}
        self.post(body)
        self.post(body)
        self.assertEqual(len(self.rows()), 1)

    def test_path_as_project_is_rejected(self):
        response = self.post(
            {"project": "/home/student/codetime",
             "time": codetime.now().isoformat()}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])

    def test_bad_time_is_rejected(self):
        response = self.post({"project": "alpha", "time": "not a time"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])

    def test_missing_field_is_rejected(self):
        response = self.post({"project": "alpha"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
