import os
import tempfile
import unittest

import tracker_auth

try:
    from fastapi.testclient import TestClient

    from webapp.main import create_app
except ImportError:  # the web libraries are optional for the CLI tests
    TestClient = None
    create_app = None


@unittest.skipIf(TestClient is None, "FastAPI is not installed.")
class TestTrackerState(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(create_app(), base_url="http://127.0.0.1:47625")

    def tearDown(self):
        if self.old_home is None:
            del os.environ["CODETIME_HOME"]
        else:
            os.environ["CODETIME_HOME"] = self.old_home
        self.folder.cleanup()

    def test_no_token_file_rejects_everything(self):
        response = self.client.get("/tracker/state")
        self.assertEqual(response.status_code, 401)

    def test_missing_token_header_is_rejected(self):
        tracker_auth.create_token()
        response = self.client.get("/tracker/state")
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_is_rejected(self):
        tracker_auth.create_token()
        response = self.client.get(
            "/tracker/state", headers={"X-CodeTime-Token": "wrong"}
        )
        self.assertEqual(response.status_code, 401)

    def test_correct_token_returns_state(self):
        token = tracker_auth.create_token()
        response = self.client.get(
            "/tracker/state", headers={"X-CodeTime-Token": token}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"state": "stopped", "project": None}
        )


if __name__ == "__main__":
    unittest.main()
