import unittest
from datetime import datetime, timedelta

from tracker_state import Action, State, Tracker

BASE = datetime(2026, 11, 3, 9, 0, 0)


def t(minutes=0, seconds=0):
    return BASE + timedelta(minutes=minutes, seconds=seconds)


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = Tracker()

    def test_starts_stopped(self):
        self.assertIs(self.tracker.state, State.STOPPED)

    def test_first_activity_opens_a_row(self):
        actions = self.tracker.activity("alpha", t(0))
        self.assertEqual(actions, [Action("open", "alpha", t(0))])
        self.assertIs(self.tracker.state, State.ACTIVE)

    def test_same_project_does_not_create_duplicate(self):
        self.tracker.activity("alpha", t(0))
        self.assertEqual(self.tracker.activity("alpha", t(2)), [])

    def test_switching_project_closes_old_and_opens_new(self):
        self.tracker.activity("alpha", t(0))
        actions = self.tracker.activity("beta", t(3))
        self.assertEqual(
            actions,
            [Action("close", "alpha", t(3)), Action("open", "beta", t(3))],
        )

    def test_idle_closes_at_last_activity_not_now(self):
        self.tracker.activity("alpha", t(0))
        self.assertEqual(self.tracker.check_idle(t(4, 59)), [])
        actions = self.tracker.check_idle(t(5))
        self.assertEqual(actions, [Action("close", "alpha", t(0))])
        self.assertIs(self.tracker.state, State.IDLE)

    def test_activity_after_idle_opens_a_new_row(self):
        self.tracker.activity("alpha", t(0))
        self.tracker.activity("alpha", t(2))
        actions = self.tracker.activity("alpha", t(10))
        self.assertEqual(
            actions,
            [Action("close", "alpha", t(2)), Action("open", "alpha", t(10))],
        )
        self.assertIs(self.tracker.state, State.ACTIVE)

    def test_paused_ignores_activity(self):
        self.tracker.activity("alpha", t(0))
        self.tracker.pause(t(1))
        self.assertEqual(self.tracker.activity("alpha", t(2)), [])
        self.assertIs(self.tracker.state, State.PAUSED)

    def test_pause_closes_the_open_row(self):
        self.tracker.activity("alpha", t(0))
        self.assertEqual(
            self.tracker.pause(t(1)), [Action("close", "alpha", t(1))]
        )

    def test_resume_goes_to_stopped_then_activity_reopens(self):
        self.tracker.activity("alpha", t(0))
        self.tracker.pause(t(1))
        self.tracker.resume(t(2))
        self.assertIs(self.tracker.state, State.STOPPED)
        self.assertEqual(
            self.tracker.activity("alpha", t(3)),
            [Action("open", "alpha", t(3))],
        )

    def test_event_from_the_past_is_ignored(self):
        self.tracker.activity("alpha", t(5))
        self.assertEqual(self.tracker.activity("beta", t(1)), [])
        self.assertEqual(self.tracker.project, "alpha")

    def test_stop_closes_the_open_row(self):
        self.tracker.activity("alpha", t(0))
        self.assertEqual(
            self.tracker.stop(t(2)), [Action("close", "alpha", t(2))]
        )
        self.assertIs(self.tracker.state, State.STOPPED)

    def test_pause_when_stopped_does_nothing(self):
        self.assertEqual(self.tracker.pause(t(0)), [])
        self.assertIs(self.tracker.state, State.STOPPED)


if __name__ == "__main__":
    unittest.main()
