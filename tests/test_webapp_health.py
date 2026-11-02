import unittest

try:
    from fastapi.testclient import TestClient

    from webapp.main import create_app
except ImportError:  # the web libraries are optional for the CLI tests
    TestClient = None
    create_app = None


@unittest.skipIf(
    TestClient is None,
    "FastAPI is not installed. Run: pip install -r requirements-dev.txt",
)
class TestHealth(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(create_app())

    def test_health_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_unknown_route_returns_404(self):
        response = self.client.get("/does-not-exist")

        self.assertEqual(response.status_code, 404)

    def test_api_documentation_is_generated(self):
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"]["title"], "CodeTime")
        self.assertIn("/health", response.json()["paths"])


if __name__ == "__main__":
    unittest.main()
