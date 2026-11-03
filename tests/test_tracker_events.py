import unittest
from datetime import datetime, timedelta

from codetime import CodeTimeError
from tracker_events import clean_project, clean_time, parse_event

NOW = datetime(2026, 11, 3, 9, 0, 0)


class TestProject(unittest.TestCase):
    def test_plain_name_is_accepted(self):
        self.assertEqual(clean_project("codetime"), "codetime")

    def test_name_is_trimmed(self):
        self.assertEqual(clean_project("  codetime  "), "codetime")

    def test_non_text_is_rejected(self):
        for bad in (None, 5, ["a"], {"a": 1}):
            with self.assertRaises(CodeTimeError):
                clean_project(bad)

    def test_empty_or_blank_is_rejected(self):
        for bad in ("", "   "):
            with self.assertRaises(CodeTimeError):
                clean_project(bad)

    def test_too_long_is_rejected(self):
        with self.assertRaises(CodeTimeError):
            clean_project("a" * 101)
        self.assertEqual(clean_project("a" * 100), "a" * 100)

    def test_paths_are_rejected(self):
        for bad in ("/home/student/codetime", "a/b", "a\\b"):
            with self.assertRaises(CodeTimeError):
                clean_project(bad)

    def test_control_characters_are_rejected(self):
        for bad in ("a\nb", "a\tb", "a\x00b", "a\x7fb"):
            with self.assertRaises(CodeTimeError):
                clean_project(bad)


class TestTime(unittest.TestCase):
    def test_valid_time_is_parsed(self):
        self.assertEqual(
            clean_time("2026-11-03T08:59:00", NOW),
            datetime(2026, 11, 3, 8, 59, 0),
        )

    def test_non_text_is_rejected(self):
        for bad in (None, 5, ["x"]):
            with self.assertRaises(CodeTimeError):
                clean_time(bad, NOW)

    def test_garbage_is_rejected(self):
        with self.assertRaises(CodeTimeError):
            clean_time("not a time", NOW)

    def test_future_limit(self):
        ok = (NOW + timedelta(minutes=5)).isoformat()
        bad = (NOW + timedelta(minutes=5, seconds=1)).isoformat()
        self.assertEqual(clean_time(ok, NOW), NOW + timedelta(minutes=5))
        with self.assertRaises(CodeTimeError):
            clean_time(bad, NOW)

    def test_past_limit(self):
        ok = (NOW - timedelta(days=1)).isoformat()
        bad = (NOW - timedelta(days=1, seconds=1)).isoformat()
        self.assertEqual(clean_time(ok, NOW), NOW - timedelta(days=1))
        with self.assertRaises(CodeTimeError):
            clean_time(bad, NOW)

    def test_timezone_time_becomes_naive(self):
        result = clean_time(datetime.now().astimezone().isoformat(), datetime.now())
        self.assertIsNone(result.tzinfo)


class TestParseEvent(unittest.TestCase):
    def test_good_message(self):
        data = {"project": "codetime", "time": "2026-11-03T08:59:00"}
        self.assertEqual(
            parse_event(data, NOW),
            ("codetime", datetime(2026, 11, 3, 8, 59, 0)),
        )

    def test_extra_fields_are_ignored(self):
        data = {"project": "a", "time": "2026-11-03T08:59:00", "file": "x.py"}
        self.assertEqual(parse_event(data, NOW)[0], "a")

    def test_missing_fields_are_rejected(self):
        for bad in ({}, {"project": "a"}, {"time": "2026-11-03T08:59:00"}):
            with self.assertRaises(CodeTimeError):
                parse_event(bad, NOW)

    def test_non_object_is_rejected(self):
        for bad in (None, "text", ["a"], 5):
            with self.assertRaises(CodeTimeError):
                parse_event(bad, NOW)


if __name__ == "__main__":
    unittest.main()
