import os
import tempfile
import unittest
from contextlib import closing
from unittest import skipIf

import account_login
import accounts
import codetime

try:
    from fastapi.testclient import TestClient
    from webapp.main import create_app
except ImportError:
    TestClient = None
    create_app = None


@skipIf(TestClient is None, "FastAPI test dependencies are not installed")
class TestReportPreferencesAPI(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("CODETIME_HOME")
        os.environ["CODETIME_HOME"] = self.folder.name
        self.client = TestClient(
            create_app(),
            base_url="http://127.0.0.1:47626",
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

    def test_report_preferences_require_login(self):
        get_response = self.client.get("/api/report-preferences")
        put_response = self.client.put(
            "/api/report-preferences",
            json={"enabled": True, "frequency": "daily"},
        )

        self.assertEqual(get_response.status_code, 401)
        self.assertEqual(put_response.status_code, 401)

    def test_accounts_only_see_their_own_report_preferences(self):
        account_a = self.create_account("account-a@example.com")
        account_b = self.create_account("account-b@example.com")

        response_a = self.client.get(
            "/api/report-preferences",
            headers=account_a,
        )
        response_b = self.client.get(
            "/api/report-preferences",
            headers=account_b,
        )

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(
            response_a.json()["email"],
            "account-a@example.com",
        )
        self.assertEqual(
            response_b.json()["email"],
            "account-b@example.com",
        )

        save_response = self.client.put(
            "/api/report-preferences",
            headers=account_a,
            json={"enabled": True, "frequency": "weekly"},
        )

        self.assertEqual(save_response.status_code, 200)

        updated_a = self.client.get(
            "/api/report-preferences",
            headers=account_a,
        ).json()
        unchanged_b = self.client.get(
            "/api/report-preferences",
            headers=account_b,
        ).json()

        self.assertTrue(updated_a["enabled"])
        self.assertEqual(updated_a["frequency"], "weekly")
        self.assertEqual(updated_a["email"], "account-a@example.com")

        self.assertFalse(unchanged_b["enabled"])
        self.assertEqual(unchanged_b["frequency"], "daily")
        self.assertEqual(unchanged_b["email"], "account-b@example.com")

    def test_invalid_frequency_is_rejected(self):
        account = self.create_account("frequency@example.com")

        response = self.client.put(
            "/api/report-preferences",
            headers=account,
            json={"enabled": True, "frequency": "hourly"},
        )

        self.assertEqual(response.status_code, 400)

        current = self.client.get(
            "/api/report-preferences",
            headers=account,
        ).json()
        self.assertFalse(current["enabled"])
        self.assertEqual(current["frequency"], "daily")


if __name__ == "__main__":
    unittest.main()
