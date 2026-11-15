"""Tests for CodeTime's system activity provider."""

import unittest

from tracker_service import _read_idle_seconds


class TestReadIdleSeconds(unittest.TestCase):
    def test_accepts_zero_idle_seconds(self):
        self.assertEqual(_read_idle_seconds(lambda: 0), 0)

    def test_accepts_valid_idle_seconds(self):
        self.assertEqual(_read_idle_seconds(lambda: 12.5), 12.5)

    def test_returns_none_when_unavailable(self):
        self.assertIsNone(_read_idle_seconds(lambda: None))

    def test_returns_none_when_provider_fails(self):
        def failing_provider():
            raise OSError("Activity service unavailable")

        self.assertIsNone(_read_idle_seconds(failing_provider))

    def test_rejects_negative_idle_seconds(self):
        self.assertIsNone(_read_idle_seconds(lambda: -1))

    def test_rejects_boolean_values(self):
        self.assertIsNone(_read_idle_seconds(lambda: True))
        self.assertIsNone(_read_idle_seconds(lambda: False))

    def test_rejects_text_values(self):
        self.assertIsNone(_read_idle_seconds(lambda: "10"))

    def test_rejects_infinite_values(self):
        self.assertIsNone(_read_idle_seconds(lambda: float("inf")))

    def test_rejects_nan(self):
        self.assertIsNone(_read_idle_seconds(lambda: float("nan")))


if __name__ == "__main__":
    unittest.main()
