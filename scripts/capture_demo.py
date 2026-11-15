"""Record the visible official Raven simulator and trim its measured preroll.

Run this on a desktop with a graphical session. The app supplies scripted gaze
while Raven's own Record control captures its simulator stream. No UI is drawn
or composited by this script.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DURATION = 68.0
SCREENSHOTS = {
    "01-focus.png": 0.5,
    "02-reminder.png": 4,
    "03-gaze.png": 10,
    "04-distance.png": 32,
    "05-complete.png": 62,
    "06-eye-rest.png": 55,
}


def timestamp(log, marker):
    match = re.search(rf"{re.escape(marker)}[^\n]*monotonic=([0-9.]+)", log)
    if match is None:
        raise RuntimeError(f"The simulator did not report {marker}.")
    return float(match.group(1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "media/demo-silent.mp4")
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--preroll", type=float, default=3.0)
    args = parser.parse_args()
    if args.delay < 0 or args.preroll < 0:
        parser.error("--delay and --preroll must be zero or positive")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("QT_QPA_PLATFORM", None)
    with tempfile.TemporaryDirectory(prefix="ease-official-") as temporary:
        raw_recording = Path(temporary) / "official-recording.mp4"
        command = [sys.executable, str(ROOT / "live_demo.py"), "--delay", str(args.delay),
                   "--record", "--preroll", str(args.preroll), "--record-output", str(raw_recording),
                   "--exit-after-save"]
        print("Opening the official Raven simulator. Keep the window visible while it records.", flush=True)
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=args.delay + args.preroll + DURATION + 90)
        print(result.stdout)
        (output.parent / "recording.log").write_text(result.stdout)
        if result.returncode or not raw_recording.exists():
            raise RuntimeError("The official simulator recording did not finish and save. See recording.log.")
        trim = timestamp(result.stdout, "EASE_DEMO_START") - timestamp(result.stdout, "EASE_RECORD_T0")
        if trim < 0:
            raise RuntimeError("The simulator reported an invalid recording timeline.")
        subprocess.run(["ffmpeg", "-y", "-ss", f"{trim:.6f}", "-i", str(raw_recording),
                        "-t", str(DURATION), "-an", "-c:v", "libx264", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)], check=True)
    for name, seconds in SCREENSHOTS.items():
        subprocess.run(["ffmpeg", "-y", "-ss", str(seconds), "-i", str(output),
                        "-frames:v", "1", str(output.parent / name)], check=True)
    print(f"Saved the official simulator video and six frame captures. Trimmed {trim:.3f}s of preroll.")


if __name__ == "__main__":
    main()
