"""Ease — a quiet, gaze-led pause for Raven Prism."""
import math
import os
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QSettings, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget
from raven_framework import Button, Container, RavenApp, RunApp
from raven_framework.helpers.utils_light import is_raven_device
from raven_framework.helpers.font_utils import load_font_family
from raven_framework.peripherals.eye_control import EyeControl

MINT = "#BCF7D1"
WHITE = "#F4F6F0"
MUTED = "#A5AEA8"
def valid_gaze(position, width=720, height=720):
    try:
        return len(position) == 2 and all(math.isfinite(float(value)) for value in position) and 0 <= position[0] < width and 0 <= position[1] < height
    except (TypeError, ValueError):
        return False


TARGETS = ((260, 305), (400, 305), (330, 245), (330, 375))
HOLD_SECONDS = 5.0
FAR_SECONDS = 20.0
CLOSED_SECONDS = 10.0


@dataclass
class ClosureRest:
    """Estimate recovered tracking-loss intervals, never verify eyelid closure."""
    stable: float = 0.0
    loss: float = 0.0
    recovery: float = 0.0
    accepted: float = 0.0
    armed: bool = False
    signal_too_long: bool = False
    chime_due: bool = False
    chimed: bool = False

    def advance(self, seconds, tracked):
        if not tracked:
            self.recovery = 0.0
            self.stable = 0.0
            if self.armed:
                self.loss += seconds
                self.signal_too_long = self.loss > 15
                if not self.chimed and not self.signal_too_long and self.accepted + self.loss >= CLOSED_SECONDS:
                    self.chime_due = True
                    self.chimed = True
            return
        if self.loss:
            self.recovery += seconds
            if self.recovery < 0.25:
                return
            if 0.5 <= self.loss <= 15:
                self.accepted += self.loss
            self.loss = 0.0
            self.recovery = 0.0
            self.armed = False
            self.chimed = False
        self.stable += seconds
        if self.stable >= 0.5:
            self.armed = True
            self.signal_too_long = False


@dataclass
class BreakSession:
    """Elapsed-time state shared by the live app and reproducible media capture."""
    interval_minutes: int = 20
    phase: str = "focus"
    remaining: float = 1200.0
    target_index: int = 0
    hold: float = 0.0
    paused: bool = False
    elapsed: float = 0.0
    completed: int = 0
    closure: ClosureRest = field(default_factory=ClosureRest)

    def start(self):
        self.phase = "gaze"
        self.target_index = 0
        self.hold = 0.0
        self.paused = False
        self.closure = ClosureRest()

    def resume_work(self, snooze=False):
        self.phase = "focus"
        self.remaining = 300.0 if snooze else self.interval_minutes * 60.0
        self.paused = False
        self.hold = 0.0

    def interrupt_tracking(self):
        self.hold = 0.0
        accepted = self.closure.accepted
        self.closure = ClosureRest(accepted=accepted)

    def advance(self, seconds, gaze=None):
        seconds = max(0.0, seconds)
        self.elapsed += seconds
        if self.paused:
            return
        if self.phase == "focus":
            self.remaining = max(0.0, self.remaining - seconds)
            if self.remaining == 0:
                self.phase = "reminder"
        elif self.phase == "gaze":
            target = TARGETS[self.target_index]
            nearby = gaze is not None and math.dist(target, gaze) <= 55
            if nearby:
                self.hold = min(HOLD_SECONDS, self.hold + seconds)
            elif gaze is not None:
                self.hold = 0.0
            # Missing gaze freezes progress so natural blinks remain welcome.
            if self.hold >= HOLD_SECONDS:
                self.target_index += 1
                self.hold = 0.0
                if self.target_index == len(TARGETS):
                    self.phase = "far"
                    self.remaining = FAR_SECONDS
        elif self.phase == "far":
            self.remaining = max(0.0, self.remaining - seconds)
            if self.remaining == 0:
                self.phase = "closed"
                self.closure = ClosureRest()
        elif self.phase == "closed":
            self.closure.advance(seconds, gaze is not None)
            if self.closure.accepted >= CLOSED_SECONDS:
                self.phase = "done"
                self.completed += 1
                self.remaining = 4.0
        elif self.phase == "done":
            self.remaining = max(0.0, self.remaining - seconds)
            if self.remaining == 0:
                self.resume_work()


def stroke(painter, path, color, width=2):
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.fillPath(stroker.createStroke(path), QColor(color))


class CalmButton(Button):
    """Raven dwell and click behavior with the application's pill treatment."""
    def set_text(self, text):
        super().set_text(text)
        self.setAccessibleName(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw(painter)
        painter.end()

    def draw(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.background_color)
        painter.setPen(QPen(self.outline_color, 1))
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 26, 26)
        painter.fillPath(pill, self.background_color)
        stroke(painter, pill, self.outline_color, 1)
        font = QFont("Inter 24pt")
        font.setPixelSize(self.text_size)
        label = QPainterPath()
        label.setFillRule(Qt.FillRule.WindingFill)
        label.addText(0, 0, font, self.text)
        bounds = label.boundingRect()
        if self.progress > 0:
            painter.setPen(QPen(QColor(WHITE), 3))
            painter.drawLine(QPointF(24, self.height()-6), QPointF(24+(self.width()-48)*self.progress/100, self.height()-6))
        painter.translate((self.width()-bounds.width())/2-bounds.x(), (self.height()-bounds.height())/2-bounds.y())
        painter.setBrush(self.text_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(label)


class BreakCanvas(QWidget):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.setFixedSize(620, 620)

    def text(self, painter, x, y, text, size=28, color=WHITE, weight=QFont.Weight.Normal):
        font = QFont("Inter 24pt")
        font.setPixelSize(size)
        font.setWeight(weight)
        painter.setFont(font)
        painter.setPen(QColor(color))
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        path.addText(x, y, font, text)
        painter.fillPath(path, QColor(color))

    def paintEvent(self, event):
        p = QPainter(self)
        self.draw(p)
        p.end()

    def draw(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#000000"))
        m = self.model
        if m.phase == "far" and m.remaining < 17:
            p.setOpacity(0.35)
        self.text(p, 32, 49, "ease", 24, MINT, QFont.Weight.Medium)
        self.text(p, 447, 49, "RAVEN", 18, MUTED)
        p.setPen(QPen(QColor("#344039"), 1))
        p.drawLine(32, 73, 588, 73)
        if m.phase == "focus":
            self.text(p, 218, 145, "Room to focus.", 38, WHITE, QFont.Weight.Medium)
            self.text(p, 218, 188, "A little pause, when it’s time.", 23, MUTED)
            center = QPointF(400, 315)
            self.ring(p, center, 81, 1 - m.remaining / (m.interval_minutes * 60), quiet=True)
            mins, secs = divmod(math.ceil(m.remaining), 60)
            label = f"{mins:02d}:{secs:02d}"
            self.text(p, 333, 328, label, 42)
            self.text(p, 345, 356, "until a pause", 18, MUTED)
        elif m.phase == "reminder":
            self.text(p, 218, 150, "A softer moment.", 38, WHITE, QFont.Weight.Medium)
            self.text(p, 218, 194, "Let your eyes take a little break.", 23, MUTED)
            self.orbit(p, QPointF(400, 310), 64)
            self.text(p, 264, 427, "Four gentle stops. Then look far.", 21, MUTED)
        elif m.phase == "gaze":
            self.text(p, 136, 146, "Rest your gaze on the light.", 32, WHITE, QFont.Weight.Medium)
            self.text(p, 218, 187, "Blink naturally. Five seconds at each light.", 21, MUTED)
            for index, (x, y) in enumerate(TARGETS):
                if index < m.target_index:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#6F9B80"))
                    p.drawEllipse(QPointF(x, y), 4, 4)
            x, y = TARGETS[m.target_index]
            self.orbit(p, QPointF(x, y), 22)
            self.ring(p, QPointF(x, y), 47, m.hold / HOLD_SECONDS)
            self.text(p, 241, 463, f"{m.target_index + 1} of 4  ·  Stay comfortable", 22, MUTED)
        elif m.phase == "far":
            self.text(p, 218, 149, "Look into the distance.", 32, WHITE, QFont.Weight.Medium)
            self.text(p, 218, 191, "Find something across the room.", 22, MUTED)
            self.landscape(p)
            self.text(p, 381, 379, str(math.ceil(m.remaining)), 46, MINT)
            self.text(p, 293, 428, "Let the display leave your focus.", 21, MUTED)
        elif m.phase == "closed":
            self.text(p, 190, 149, "Close gently. Rest a little.", 32, WHITE, QFont.Weight.Medium)
            self.text(p, 218, 191, "Open your eyes when you hear the chime.", 20, MUTED)
            p.setPen(QPen(QColor(MINT), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(330, 247, 140, 70), 180*16, 180*16)
            p.drawLine(350, 310, 343, 325)
            p.drawLine(400, 317, 400, 334)
            p.drawLine(450, 310, 457, 325)
            estimate = min(CLOSED_SECONDS, m.closure.accepted + m.closure.loss)
            self.text(p, 342, 390, f"{estimate:.0f} / 10 s", 36, MINT)
            status = "Ready · close when comfortable" if m.closure.armed else "Tracking needed · look ahead"
            if m.closure.loss:
                status = "Tracking lost · rest estimated"
            if m.closure.signal_too_long:
                status = "Signal lost too long · open and retry"
            self.text(p, 218, 433, status, 20, MUTED)
            if not is_raven_device():
                self.text(p, 218, 463, "Desktop · hold C to simulate closure", 18, MUTED)
        else:
            self.text(p, 218, 150, "Welcome back.", 38, WHITE, QFont.Weight.Medium)
            self.text(p, 218, 193, "A small pause, just for you.", 23, MUTED)
            self.orbit(p, QPointF(400, 305), 63)
            p.setPen(QPen(QColor(MINT), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            check = QPainterPath(QPointF(380, 307))
            check.lineTo(395, 321)
            check.lineTo(423, 289)
            stroke(p, check, MINT, 3)
            self.text(p, 218, 418, f"20 s gaze · {m.closure.accepted:.1f} s estimated rest", 22, MINT)
            self.text(p, 218, 451, "Next pause scheduled.", 20, MUTED)
        if m.paused:
            self.text(p, 32, 586, "Paused", 20, MINT)
        else:
            self.text(p, 32, 586, "Take it gently.", 18, MUTED)

    def export_frame(self):
        """Render the live drawing routines directly, without a window backing store."""
        image = QImage(self.size(), QImage.Format.Format_RGB32)
        image.fill(QColor("#000000"))
        painter = QPainter(image)
        painter.save()
        self.draw(painter)
        painter.restore()
        for button in self.findChildren(CalmButton):
            if not button.isHidden():
                painter.save()
                painter.translate(button.x(), button.y())
                button.draw(painter)
                painter.restore()
        painter.end()
        return image

    def ring(self, painter, center, radius, progress, quiet=False):
        bounds = QRectF(center.x()-radius, center.y()-radius, radius*2, radius*2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#253B2E"), 2))
        circle = QPainterPath()
        circle.addEllipse(bounds)
        stroke(painter, circle, "#253B2E", 2)
        painter.setPen(QPen(QColor(MINT), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        arc = QPainterPath()
        arc.arcMoveTo(bounds, 90)
        arc.arcTo(bounds, 90, -max(0.01, min(1, progress))*360)
        stroke(painter, arc, MINT, 3)

    def orbit(self, painter, center, radius):
        breath = 1.0 + 0.06 * math.sin(self.model.elapsed * 1.6)
        glow = QRadialGradient(center, radius*1.6)
        glow.setColorAt(0, QColor(188, 247, 209, 75))
        glow.setColorAt(1, QColor(188, 247, 209, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius*1.6, radius*1.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(MINT), 1.5))
        outline = QPainterPath()
        outline.addEllipse(center, radius*breath, radius*breath)
        stroke(painter, outline, MINT, 1.5)
        if radius < 30:
            painter.setBrush(QColor(MINT))
            painter.drawEllipse(center, 8, 8)

    def landscape(self, painter):
        painter.setPen(QPen(QColor(MINT), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(256, 304, 545, 304)
        painter.drawLine(274, 304, 321, 267)
        painter.drawLine(321, 267, 365, 304)
        painter.drawLine(350, 304, 417, 248)
        painter.drawLine(417, 248, 478, 304)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(484, 248), 15, 15)


class EyeBreakApp(RavenApp):
    def __init__(self, parent=None, manual=False, interval=None):
        super().__init__(parent)
        load_font_family("inter")
        self.settings = QSettings("RavenMinihack", "Ease")
        minutes = interval or int(self.settings.value("interval_minutes", 20))
        if minutes not in (10, 20, 30):
            minutes = 20
        self.model = BreakSession(interval_minutes=minutes, remaining=minutes*60)
        self.manual = manual
        self.simulated_closed = False
        self.speaker = None
        self.panel = Container(width=640, height=640, spacing=10, inner_margin=10)
        self.canvas = BreakCanvas(self.model)
        self.panel.add(self.canvas, x=10, y=10)
        self.app.add(self.panel)
        self.primary = self.make_button("Take a pause", self.primary_action, 358, 486, 225)
        self.secondary = self.make_button("Pause", self.secondary_action, 444, 554, 139, secondary=True)
        self.interval = self.make_button(f"Every {minutes} min", self.cycle_interval, 218, 554, 218, secondary=True)
        self.eye = EyeControl(os.getenv("RAVEN_APP_ID", ""), os.getenv("RAVEN_APP_KEY", "")) if is_raven_device() and not manual else None
        self.last_tick = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        if not manual:
            self.timer.start(33)
        self.sync_ui()

    def make_button(self, label, callback, x, y, width, secondary=False):
        button = CalmButton(center_text=label, width=width, height=52,
                        text_size=22 if secondary else 25,
                        background_color="#000000" if secondary else MINT,
                        text_color=WHITE if secondary else "#102219",
                        outline_color="#526559" if secondary else MINT,
                        outline_width=1, corner_radius=26, scale_by=0.03,
                        dwell_time=1400, use_fill_dwell=False, use_gradient_border=False)
        button.setParent(self.canvas)
        button.move(x, y)
        button.on_clicked(callback)
        return button

    def primary_action(self):
        if self.model.phase in ("focus", "reminder"):
            self.model.start()
        elif self.model.phase == "done":
            self.model.resume_work()
        else:
            if self.model.phase == "closed":
                self.model.interrupt_tracking()
            self.model.paused = not self.model.paused
        self.sync_ui()

    def secondary_action(self):
        if self.model.phase == "focus":
            self.model.paused = not self.model.paused
        else:
            self.model.resume_work(snooze=self.model.phase == "reminder")
        self.sync_ui()

    def cycle_interval(self):
        choices = (10, 20, 30)
        self.model.interval_minutes = choices[(choices.index(self.model.interval_minutes)+1)%len(choices)]
        self.model.remaining = self.model.interval_minutes * 60
        self.settings.setValue("interval_minutes", self.model.interval_minutes)
        self.sync_ui()

    def tick(self):
        now = time.monotonic()
        delta = now - self.last_tick
        self.last_tick = now
        gaze = None
        if self.eye:
            raw = self.eye.get_gaze_position()
            if valid_gaze(raw, self.width(), self.height()):
                origin = self.canvas.mapTo(self, QPoint(0, 0))
                gaze = (raw[0]-origin.x(), raw[1]-origin.y())
        elif not is_raven_device():
            local = self.canvas.mapFromGlobal(QCursor.pos())
            gaze = (local.x(), local.y())
        if self.simulated_closed:
            gaze = None
        # Interrupted sampling invalidates an unfinished observation.
        if delta > 0.2 and self.model.phase in ("gaze", "closed"):
            self.model.interrupt_tracking()
        else:
            self.model.advance(delta, gaze)
        if self.model.closure.chime_due:
            self.model.closure.chime_due = False
            self.play_rest_chime()
        self.sync_ui()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C and not event.isAutoRepeat() and not is_raven_device():
            self.simulated_closed = True
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_C and not event.isAutoRepeat():
            self.simulated_closed = False
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def play_rest_chime(self):
        if self.manual:
            return
        if is_raven_device():
            import io
            import struct
            import wave
            from raven_framework.peripherals.speaker import Speaker
            audio = io.BytesIO()
            with wave.open(audio, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                samples = [int(5000 * math.sin(2*math.pi*660*i/24000) * math.sin(math.pi*i/7200)) for i in range(7200)]
                wav.writeframes(struct.pack("<" + "h"*len(samples), *samples))
            if self.speaker is None:
                self.speaker = Speaker()
            self.speaker.play_audio(audio.getvalue())
        else:
            QApplication.beep()

    def sync_ui(self):
        m = self.model
        labels = {"focus": "Take a pause", "reminder": "Begin", "gaze": "Resume" if m.paused else "Pause", "far": "Resume" if m.paused else "Pause", "closed": "Resume" if m.paused else "Pause", "done": "Back to work"}
        self.primary.set_text(labels[m.phase])
        self.secondary.set_text(("Resume" if m.paused else "Pause") if m.phase == "focus" else ("In 5 min" if m.phase == "reminder" else "Skip"))
        self.interval.setVisible(m.phase == "focus")
        self.interval.set_text(f"Every {m.interval_minutes} min")
        self.canvas.update()


if __name__ == "__main__":
    RunApp.run(lambda: EyeBreakApp(), app_id=os.getenv("RAVEN_APP_ID", ""), app_key=os.getenv("RAVEN_APP_KEY", ""))
