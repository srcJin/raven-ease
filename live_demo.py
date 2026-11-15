"""Run Ease's timed demonstration inside Raven's official simulator window.

This entry point supplies scripted gaze input for a screen recording. It does
not export, composite, or record any pixels. Normal main.py behavior is unchanged.
"""
import argparse
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton
from raven_framework import RunApp

from main import EyeBreakApp, TARGETS

DURATION = 68.0
STEP = 1 / 120


class LiveDemo(EyeBreakApp):
    def __init__(self, delay, record=False, preroll=3.0, record_output=None):
        super().__init__(manual=True, interval=20)
        self.model.remaining = 3.0
        self.sync_ui()
        self.record_requested = record
        self.preroll = preroll
        self.record_output = record_output
        self.save_dialog_accepted = False
        self.original_output_mtime = record_output.stat().st_mtime_ns if record_output and record_output.exists() else None
        self.record_button = None
        self.recording_stopped = False
        for button in (self.primary, self.secondary, self.interval):
            button.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self.save_official_recording)
        self.demo_started_at = None
        self.demo_time = 0.0
        self.begin_requested = False
        self.last_phase = self.model.phase
        self.demo_timer = QTimer(self)
        self.demo_timer.timeout.connect(self.advance_demo)
        print(f"EASE_DEMO_READY delay={delay:.1f}s duration={DURATION:.1f}s", flush=True)
        QTimer.singleShot(round(delay * 1000), self.prepare_demo)

    def prepare_demo(self):
        if not self.record_requested:
            self.start_demo()
            return
        self.record_button = next((button for button in self.window().findChildren(QPushButton)
                                   if button.toolTip() == "Record the simulator view to an mp4"), None)
        if self.record_button is None:
            print("EASE_DEMO_ERROR Official simulator Record control was not found.", flush=True)
            return
        self.record_button.click()
        print(f"EASE_RECORD_T0 monotonic={time.monotonic():.6f} preroll={self.preroll:.1f}s", flush=True)
        QTimer.singleShot(round(self.preroll * 1000), self.start_demo)

    def save_official_recording(self):
        if self.save_dialog_accepted and self.record_output.exists() and self.record_output.stat().st_size > 0 and self.record_output.stat().st_mtime_ns != self.original_output_mtime:
            self.save_timer.stop()
            print(f"EASE_RECORD_SAVED {self.record_output}", flush=True)
            return
        for window in QApplication.topLevelWidgets():
            if isinstance(window, QFileDialog) and window.isVisible() and window.windowTitle() == "Save recording":
                window.setDirectory(str(self.record_output.parent))
                window.selectFile(self.record_output.name)
                self.save_dialog_accepted = True
                window.accept()
                return

    def start_demo(self):
        self.demo_started_at = time.monotonic()
        print(f"EASE_DEMO_START DEMO_T0 monotonic={self.demo_started_at:.6f}", flush=True)
        self.demo_timer.start(16)

    def advance_demo(self):
        elapsed = min(DURATION, time.monotonic() - self.demo_started_at)
        # Feed the normal state model a stable stream of simulated samples.
        # Catch up after a delayed UI frame without changing the real-time schedule.
        while self.demo_time + STEP <= elapsed:
            self.demo_time += STEP
            if self.demo_time >= 7 and not self.begin_requested:
                self.primary_action()
                self.begin_requested = True
            gaze = (330, 305)
            if self.model.phase == "gaze" and self.demo_time >= 8:
                gaze = TARGETS[self.model.target_index]
            if 49.5 <= self.demo_time < 59.8:
                gaze = None
            if self.model.phase == "done":
                # Keep the real completion screen visible for the closing narration.
                self.model.elapsed += STEP
            else:
                self.model.advance(STEP, gaze)
            if self.model.closure.chime_due:
                self.model.closure.chime_due = False
                QApplication.beep()
                print(f"EASE_DEMO_CHIME t={self.demo_time:.3f}", flush=True)
            if self.model.phase != self.last_phase:
                self.last_phase = self.model.phase
                print(f"EASE_DEMO_PHASE t={self.demo_time:.3f} phase={self.model.phase}", flush=True)
        self.sync_ui()
        if elapsed >= DURATION:
            self.demo_timer.stop()
            if self.record_button is not None and not self.recording_stopped:
                self.recording_stopped = True
                if self.record_output is not None:
                    self.save_timer.start(100)
                self.record_button.click()
                print(f"EASE_RECORD_STOP monotonic={time.monotonic():.6f}", flush=True)
            print(f"EASE_DEMO_FINISHED t={DURATION:.1f} phase={self.model.phase} gaze=20s estimated_rest={self.model.closure.accepted:.2f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds before the 68-second sequence starts.")
    parser.add_argument("--record", action="store_true", help="Use the official simulator Record control.")
    parser.add_argument("--preroll", type=float, default=3.0, help="Seconds between recording start and demo start.")
    parser.add_argument("--record-output", type=Path, help="Save the official recording through its Qt Save dialog.")
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must be zero or positive")
    if args.preroll < 0:
        parser.error("--preroll must be zero or positive")
    if args.record_output:
        args.record = True
        args.record_output = args.record_output.resolve()
        args.record_output.parent.mkdir(parents=True, exist_ok=True)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    # RunApp has its own deployment CLI, so consume only this entry point's options.
    sys.argv = [sys.argv[0]]
    RunApp.run(lambda: LiveDemo(args.delay, args.record, args.preroll, args.record_output), app_id="", app_key="")


if __name__ == "__main__":
    main()
