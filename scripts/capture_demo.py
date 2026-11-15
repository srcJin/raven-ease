"""Export real application drawing routines and encode a simulator walkthrough."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import copy
from concurrent.futures import ProcessPoolExecutor
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication
from main import BreakSession, EyeBreakApp, TARGETS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "media"
FPS = 24
DURATION = 68
SHOTS = {0: "01-focus.png", 4*FPS: "02-reminder.png", 10*FPS: "03-gaze.png", 32*FPS: "04-distance.png", 62*FPS: "05-complete.png", 55*FPS: "06-eye-rest.png"}


def draw_text(painter, font, x, y, text):
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    path.addText(x, y, font, text)
    painter.fillPath(path, painter.pen().color())


def render_frame(item):
    frame, model = item
    qt = QApplication([])
    app = EyeBreakApp(manual=True, interval=20)
    app.model = model
    app.canvas.model = model
    app.sync_ui()
    screenshot = app.canvas.export_frame()
    if frame in SHOTS:
        screenshot.save(str(OUT / SHOTS[frame]))
    image = QImage(1280, 900, QImage.Format.Format_RGB32)
    image.fill(QColor("#101613"))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#BCF7D1"))
    font = QFont("Inter 24pt"); font.setPixelSize(26)
    draw_text(p, font, 60, 70, "EASE")
    font.setPixelSize(18)
    p.setPen(QColor("#A5AEA8"))
    draw_text(p, font, 945, 70, "RAVEN · SIMULATOR DEMO")
    p.setPen(QColor("#314638"))
    p.setBrush(QColor("#000000"))
    p.drawRoundedRect(QRectF(317, 117, 646, 646), 26, 26)
    p.drawImage(QPoint(330, 130), screenshot)
    font.setPixelSize(22)
    captions = (
        (3, "A quiet companion for focused work."),
        (7, "A gentle reminder. You choose when to begin."),
        (28, "Four gentle points. Five seconds each. Blink naturally."),
        (49, "Look at something distant in the real world for 20 seconds."),
        (60, "Close gently. Tracking loss estimates rest; reopening confirms the interval."),
        (65, "20 seconds of gaze movement. 10 seconds of estimated eye rest."),
        (68, "Ease for Raven Prism  ·  github.com/srcJin/raven-ease"),
    )
    caption = next(text for until, text in captions if frame/FPS < until)
    label = QPainterPath()
    label.setFillRule(Qt.FillRule.WindingFill)
    label.addText(0, 0, font, caption)
    p.translate((1280-label.boundingRect().width())/2, 833)
    p.fillPath(label, QColor("#F4F6F0"))
    p.end()
    image.save(str(OUT / "frames" / f"{frame:05d}.png"))
    return frame


def main():
    (OUT / "frames").mkdir(parents=True, exist_ok=True)
    model = BreakSession(remaining=3)
    timeline = []
    for frame in range(DURATION * FPS):
        t = frame / FPS
        if frame == 7*FPS:
            model.start()
        gaze = (330, 305)
        if model.phase == "gaze" and t >= 8:
            gaze = TARGETS[model.target_index]
        if 49.5 <= t < 59.8:
            gaze = None
        model.advance(1/FPS, gaze)
        timeline.append((frame, copy.deepcopy(model)))
    # Qt 6.12 offscreen develops stale clipped regions after repeated exports.
    # A fresh process per frame keeps each real app render complete and reproducible.
    with ProcessPoolExecutor(max_workers=6, max_tasks_per_child=1) as pool:
        for frame in pool.map(render_frame, timeline):
            if frame % 240 == 0:
                print(f"Rendered {frame}/{len(timeline)} frames", flush=True)
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(OUT / "frames" / "%05d.png"), "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / "demo-silent.mp4")], check=True)
    print("Rendered 68 seconds with the actual app renderer and six screenshots.")


if __name__ == "__main__":
    main()
