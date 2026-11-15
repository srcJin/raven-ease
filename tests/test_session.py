import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtWidgets import QApplication
from main import EyeBreakApp
from main import BreakSession, ClosureRest, TARGETS, HOLD_SECONDS, FAR_SECONDS, valid_gaze

class SessionTests(unittest.TestCase):
    def test_reminder_waits_for_user_and_snooze(self):
        session = BreakSession(remaining=1)
        session.advance(2)
        self.assertEqual(session.phase, "reminder")
        session.advance(100)
        self.assertEqual(session.phase, "reminder")
        session.resume_work(snooze=True)
        self.assertEqual(session.remaining, 300)

    def test_each_point_needs_five_seconds_and_blinks_freeze(self):
        session = BreakSession(); session.start()
        session.advance(3, TARGETS[0])
        session.advance(0.2, None)
        self.assertEqual(session.hold, 3)
        session.advance(1.9, TARGETS[0])
        self.assertEqual(session.target_index, 0)
        session.advance(0.11, TARGETS[0])
        self.assertEqual(session.target_index, 1)
        session.advance(2, TARGETS[1])
        session.advance(0.1, (0, 0))
        self.assertEqual(session.hold, 0)

    def test_pause_freezes_hold(self):
        session = BreakSession(); session.start()
        session.advance(2, TARGETS[0]); session.paused = True
        session.advance(10, TARGETS[0])
        self.assertEqual(session.hold, 2)
        self.assertEqual(session.target_index, 0)

    def test_complete_flow_requires_distance_and_recovered_rest(self):
        session = BreakSession(); session.start()
        for target in TARGETS:
            session.advance(HOLD_SECONDS, target)
        self.assertEqual(session.phase, "far")
        session.advance(FAR_SECONDS-0.1)
        self.assertEqual(session.phase, "far")
        session.advance(0.2)
        self.assertEqual(session.phase, "closed")
        session.advance(0.5, (330, 305))
        session.advance(10, None)
        self.assertEqual(session.phase, "closed")
        self.assertTrue(session.closure.chime_due)
        session.advance(0.25, (330, 305))
        self.assertEqual(session.phase, "done")
        self.assertEqual(session.completed, 1)
        session.advance(4)
        self.assertEqual(session.phase, "focus")

    def test_closure_needs_baseline_and_filters_blinks_and_faults(self):
        rest = ClosureRest()
        rest.advance(10, False); rest.advance(0.5, True)
        self.assertEqual(rest.accepted, 0)
        rest.advance(0.2, False); rest.advance(0.25, True)
        self.assertEqual(rest.accepted, 0)
        rest.advance(0.5, True); rest.advance(16, False)
        self.assertTrue(rest.signal_too_long)
        rest.advance(0.25, True)
        self.assertEqual(rest.accepted, 0)

    def test_multiple_recovered_closures_accumulate(self):
        rest = ClosureRest()
        for _ in range(2):
            rest.advance(0.5, True)
            rest.advance(5, False)
            rest.advance(0.25, True)
        self.assertEqual(rest.accepted, 10)

    def test_invalid_coordinates_are_not_tracking(self):
        for point in (None, (-1, -1), (float("nan"), 50), (720, 0), (1,), "xy"):
            self.assertFalse(valid_gaze(point))
        self.assertTrue(valid_gaze((350, 280)))

    def test_interrupted_polling_clears_candidate_preserves_accepted(self):
        session = BreakSession(phase="closed")
        session.closure.accepted = 5
        session.closure.advance(0.5, True)
        session.closure.advance(4, False)
        session.interrupt_tracking()
        session.advance(0.5, (330, 305))
        self.assertEqual(session.closure.accepted, 5)
        self.assertEqual(session.closure.loss, 0)
        self.assertFalse(session.closure.chimed)

    def test_rejected_candidate_can_chime_again(self):
        rest = ClosureRest()
        rest.advance(0.5, True); rest.advance(10, False)
        self.assertTrue(rest.chime_due)
        rest.chime_due = False
        rest.advance(6, False); rest.advance(0.5, True)
        rest.advance(10, False)
        self.assertTrue(rest.chime_due)
        self.assertEqual(rest.accepted, 0)

    def test_skip_and_paused_work(self):
        session = BreakSession(remaining=100, paused=True)
        session.advance(20)
        self.assertEqual(session.remaining, 100)
        session.start(); session.resume_work()
        self.assertFalse(session.paused)
        self.assertEqual(session.phase, "focus")

class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_pausing_eye_rest_clears_unobserved_candidate(self):
        app = EyeBreakApp(manual=True)
        app.model.phase = "closed"
        app.model.closure.accepted = 5
        app.model.closure.armed = True
        app.model.closure.loss = 4
        app.primary_action()
        self.assertTrue(app.model.paused)
        self.assertEqual(app.model.closure.loss, 0)
        self.assertEqual(app.model.closure.accepted, 5)
        app.primary_action()
        self.assertFalse(app.model.paused)
        self.assertFalse(app.model.closure.armed)
        app.close()


if __name__ == "__main__":
    unittest.main()
