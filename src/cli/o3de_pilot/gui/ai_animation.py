# O3DE Pilot GUI - AI Animation Widget
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Animated swirling circle visualisation for the AI assistant.

States:
    DORMANT       – No AI configured; blank.
    DISCONNECTED  – Provider set, not verified; pulsing red eye.
    IDLE          – Connected; slow organic breathing, green/blue glow.
    LISTENING     – Mic-reactive rings.
    THINKING      – Fast, intense glow burst.
"""

import math
from enum import Enum, auto

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QRadialGradient, QConicalGradient,
    QBrush, QPainterPath,
)
from PySide6.QtWidgets import QWidget, QSizePolicy


class AIState(Enum):
    DORMANT = auto()       # No AI configured — static, no animation
    DISCONNECTED = auto()  # Provider set but not verified — pulsing red eye
    IDLE = auto()          # Connected & verified — gentle organic animation
    LISTENING = auto()
    THINKING = auto()


class AIAnimationWidget(QWidget):
    """Swirling circle animation for the AI tab.

    Scales to fill available space while keeping a square aspect ratio.
    All drawing uses proportional coordinates so the rings look correct
    at any size.
    """

    MIN_SIZE = 80   # minimum useful diameter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(self.MIN_SIZE, self.MIN_SIZE)
        self._state = AIState.DORMANT
        self._t = 0.0              # master time counter (seconds)
        self._angle = 0.0          # primary rotation (degrees)
        self._angle2 = 0.0         # secondary ring
        self._angle3 = 0.0         # tertiary ring
        self._mic_level = 0.0      # 0‥1 normalised mic amplitude

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)       # ~60 fps

    # ── Keep square ─────────────────────────────────────────────────

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return w

    # ── State control ───────────────────────────────────────────────

    @property
    def state(self) -> AIState:
        return self._state

    def set_state(self, state: AIState):
        self._state = state
        self.update()

    def set_mic_level(self, level: float):
        """Set microphone input level (0‥1)."""
        self._mic_level = max(0.0, min(1.0, level))

    # ── Pulse helpers ───────────────────────────────────────────────

    def _red_pulse(self) -> float:
        """Constant-rate sinusoidal pulse for disconnected state (0‥1).
        Steady 1 Hz heartbeat."""
        return 0.5 + 0.5 * math.sin(self._t * 2.0 * math.pi * 1.0)

    def _organic_pulse(self) -> float:
        """Organic breathing pulse for idle — mix of slow sin waves.
        ~0.3 Hz base with subtle harmonics for a living feel."""
        base = math.sin(self._t * 2.0 * math.pi * 0.3)
        harmonic = 0.3 * math.sin(self._t * 2.0 * math.pi * 0.7 + 0.5)
        micro = 0.15 * math.sin(self._t * 2.0 * math.pi * 1.3 + 1.2)
        raw = base + harmonic + micro
        # Normalise to 0‥1
        return max(0.0, min(1.0, (raw + 1.45) / 2.9))

    def _thinking_pulse(self) -> float:
        """Fast intense pulse for processing — ~2.5 Hz."""
        fast = math.sin(self._t * 2.0 * math.pi * 2.5)
        accent = 0.4 * math.sin(self._t * 2.0 * math.pi * 5.0 + 0.8)
        raw = fast + accent
        return max(0.0, min(1.0, (raw + 1.4) / 2.8))

    # ── Animation loop ──────────────────────────────────────────────

    def _tick(self):
        dt = 0.016  # ~60 fps
        self._t += dt

        if self._state == AIState.DORMANT:
            return  # nothing to animate

        # Disconnected still animates (pulsing glow) — no ring rotation
        if self._state == AIState.DISCONNECTED:
            self.update()
            return

        # Rotation speeds vary by state
        if self._state == AIState.IDLE:
            self._angle = (self._angle + 0.4) % 360
            self._angle2 = (self._angle2 - 0.25) % 360
        elif self._state == AIState.LISTENING:
            self._angle = (self._angle + 1.0) % 360
            self._angle2 = (self._angle2 - 0.7) % 360
        elif self._state == AIState.THINKING:
            self._angle = (self._angle + 3.5) % 360
            self._angle2 = (self._angle2 - 2.5) % 360
            self._angle3 = (self._angle3 + 4.5) % 360

        self.update()

    # ── Painting ────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        s = float(side)
        ox = (self.width() - side) / 2.0
        oy = (self.height() - side) / 2.0
        cx = ox + s / 2.0
        cy = oy + s / 2.0
        k = s / 200.0

        if self._state == AIState.DORMANT:
            # Faint dormant circle outline
            pen = QPen(QColor(60, 60, 60, 80), 1.5 * k)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), 50 * k, 50 * k)
            painter.end()
            return

        if self._state == AIState.DISCONNECTED:
            self._paint_disconnected(painter, cx, cy, s, k)
            painter.end()
            return

        if self._state == AIState.THINKING:
            self._paint_thinking(painter, cx, cy, s, k, ox, oy)
        elif self._state == AIState.IDLE:
            self._paint_idle(painter, cx, cy, s, k, ox, oy)
        elif self._state == AIState.LISTENING:
            self._paint_listening(painter, cx, cy, s, k, ox, oy)

        painter.end()

    # ── DISCONNECTED: pulsing red eye ───────────────────────────────

    def _paint_disconnected(self, p: QPainter, cx, cy, s, k):
        pulse = self._red_pulse()

        # Layer 1: wide outer glow
        grad = QRadialGradient(cx, cy, s * (0.35 + 0.08 * pulse))
        grad.setColorAt(0, QColor(220, 30, 30, int(50 + 60 * pulse)))
        grad.setColorAt(0.5, QColor(200, 20, 20, int(20 + 30 * pulse)))
        grad.setColorAt(1, QColor(180, 10, 10, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), s * 0.45, s * 0.45)

        # Layer 2: mid glow — tighter
        grad2 = QRadialGradient(cx, cy, s * (0.18 + 0.05 * pulse))
        grad2.setColorAt(0, QColor(255, 50, 50, int(90 + 80 * pulse)))
        grad2.setColorAt(0.6, QColor(220, 30, 30, int(40 + 40 * pulse)))
        grad2.setColorAt(1, QColor(200, 20, 20, 0))
        p.setBrush(QBrush(grad2))
        p.drawEllipse(QPointF(cx, cy), s * 0.25, s * 0.25)

        # Pulsing rings (faint, static position but alpha pulses)
        ring_alpha = int(60 + 70 * pulse)
        ring_col = QColor(200, 50, 50, ring_alpha)
        ring_dim = QColor(120, 30, 30, int(20 + 30 * pulse))
        self._draw_ring(p, cx, cy, radius=70 * k, angle=0,
                        arc_span=360, width=(1.5 + 1.0 * pulse) * k,
                        color=ring_col, fade_color=ring_col)
        self._draw_ring(p, cx, cy, radius=56 * k, angle=0,
                        arc_span=360, width=(1.0 + 0.8 * pulse) * k,
                        color=ring_dim, fade_color=ring_dim)

        # Core dot — bright red, pulsing size
        dot_r = (5 + 6 * pulse) * k
        core_col = QColor(255, int(60 + 40 * pulse), int(40 + 30 * pulse))
        p.setBrush(QBrush(core_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

        # Inner white-hot spot
        hot_r = (2 + 2 * pulse) * k
        p.setBrush(QBrush(QColor(255, 180, 160, int(120 + 100 * pulse))))
        p.drawEllipse(QPointF(cx, cy), hot_r, hot_r)

    # ── IDLE: organic breathing green/blue ──────────────────────────

    def _paint_idle(self, p: QPainter, cx, cy, s, k, ox, oy):
        pulse = self._organic_pulse()

        # Outer ambient glow
        grad = QRadialGradient(cx, cy, s * (0.30 + 0.06 * pulse))
        grad.setColorAt(0, QColor(0, 200, 180, int(25 + 35 * pulse)))
        grad.setColorAt(0.6, QColor(0, 150, 220, int(10 + 20 * pulse)))
        grad.setColorAt(1, QColor(0, 100, 200, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), s * 0.40, s * 0.40)

        # Rings — gentle orbit
        ring_alpha = int(120 + 60 * pulse)
        self._draw_ring(p, cx, cy, radius=70 * k, angle=self._angle,
                        arc_span=240, width=(2.0 + 1.0 * pulse) * k,
                        color=QColor(0, 120, 212, ring_alpha),
                        fade_color=QColor(0, 120, 212, int(40 + 30 * pulse)))
        self._draw_ring(p, cx, cy, radius=56 * k, angle=self._angle2,
                        arc_span=200, width=(1.5 + 0.8 * pulse) * k,
                        color=QColor(64, 160, 255, int(100 + 50 * pulse)),
                        fade_color=QColor(64, 160, 255, int(25 + 20 * pulse)))

        # Core dot — green/teal, organic pulse
        dot_r = (4 + 4 * pulse) * k
        core_col = QColor(int(0 + 20 * pulse), int(200 + 30 * pulse),
                          int(160 + 40 * pulse))
        p.setBrush(QBrush(core_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

        # Soft bright centre
        hot_r = (2 + 1.5 * pulse) * k
        p.setBrush(QBrush(QColor(200, 255, 240, int(80 + 60 * pulse))))
        p.drawEllipse(QPointF(cx, cy), hot_r, hot_r)

    # ── THINKING: intense fast glow ─────────────────────────────────

    def _paint_thinking(self, p: QPainter, cx, cy, s, k, ox, oy):
        pulse = self._thinking_pulse()

        # Layer 1: massive outer glow
        grad = QRadialGradient(cx, cy, s * (0.45 + 0.10 * pulse))
        grad.setColorAt(0, QColor(0, 140, 255, int(60 + 100 * pulse)))
        grad.setColorAt(0.4, QColor(0, 100, 255, int(30 + 60 * pulse)))
        grad.setColorAt(0.7, QColor(0, 60, 200, int(10 + 30 * pulse)))
        grad.setColorAt(1, QColor(0, 40, 150, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), s * 0.50, s * 0.50)

        # Layer 2: inner intense glow
        grad2 = QRadialGradient(cx, cy, s * (0.20 + 0.06 * pulse))
        grad2.setColorAt(0, QColor(80, 200, 255, int(120 + 120 * pulse)))
        grad2.setColorAt(0.5, QColor(0, 160, 255, int(60 + 80 * pulse)))
        grad2.setColorAt(1, QColor(0, 120, 220, 0))
        p.setBrush(QBrush(grad2))
        p.drawEllipse(QPointF(cx, cy), s * 0.28, s * 0.28)

        # Fast rings — three layers
        ring_a = int(180 + 75 * pulse)
        self._draw_ring(p, cx, cy, radius=70 * k, angle=self._angle,
                        arc_span=240, width=(3.0 + 2.0 * pulse) * k,
                        color=QColor(0, 150, 255, ring_a),
                        fade_color=QColor(0, 100, 220, int(50 + 40 * pulse)))
        self._draw_ring(p, cx, cy, radius=56 * k, angle=self._angle2,
                        arc_span=200, width=(2.5 + 1.5 * pulse) * k,
                        color=QColor(80, 180, 255, int(160 + 60 * pulse)),
                        fade_color=QColor(40, 140, 255, int(30 + 30 * pulse)))
        self._draw_ring(p, cx, cy, radius=84 * k, angle=self._angle3,
                        arc_span=160, width=(2.0 + 1.5 * pulse) * k,
                        color=QColor(120, 210, 255, int(140 + 80 * pulse)),
                        fade_color=QColor(80, 180, 255, int(20 + 25 * pulse)))

        # Fourth outer shimmer ring
        self._draw_ring(p, cx, cy, radius=(92 + 4 * pulse) * k,
                        angle=-self._angle * 0.7,
                        arc_span=120, width=(1.5 + 1.0 * pulse) * k,
                        color=QColor(160, 220, 255, int(60 + 80 * pulse)),
                        fade_color=QColor(100, 180, 255, int(10 + 15 * pulse)))

        # Core — bright white-blue, large pulsing
        dot_r = (6 + 8 * pulse) * k
        p.setBrush(QBrush(QColor(100, 220, 255, int(200 + 55 * pulse))))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

        # White-hot centre
        hot_r = (3 + 4 * pulse) * k
        p.setBrush(QBrush(QColor(220, 240, 255, int(180 + 75 * pulse))))
        p.drawEllipse(QPointF(cx, cy), hot_r, hot_r)

    # ── LISTENING ───────────────────────────────────────────────────

    def _paint_listening(self, p: QPainter, cx, cy, s, k, ox, oy):
        pulse = self._organic_pulse()
        mic = self._mic_level

        # Green-tinted glow
        grad = QRadialGradient(cx, cy, s * (0.35 + 0.05 * mic))
        grad.setColorAt(0, QColor(0, 220, 140, int(30 + 50 * mic + 20 * pulse)))
        grad.setColorAt(0.6, QColor(0, 180, 120, int(15 + 25 * mic)))
        grad.setColorAt(1, QColor(0, 150, 100, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), s * 0.42, s * 0.42)

        # Standard rings
        self._draw_ring(p, cx, cy, radius=70 * k, angle=self._angle,
                        arc_span=240, width=(2.5 + 0.5 * pulse) * k,
                        color=QColor(0, 120, 212, int(150 + 40 * pulse)),
                        fade_color=QColor(0, 120, 212, 50))
        self._draw_ring(p, cx, cy, radius=56 * k, angle=self._angle2,
                        arc_span=200, width=(1.8 + 0.5 * pulse) * k,
                        color=QColor(64, 160, 255, int(120 + 30 * pulse)),
                        fade_color=QColor(64, 160, 255, 30))

        # Mic-reactive ring
        extra_r = (82 + mic * 10) * k
        mic_alpha = int(80 + 140 * mic)
        self._draw_ring(p, cx, cy, radius=extra_r, angle=-self._angle,
                        arc_span=180, width=(2.5 + 1.5 * mic) * k,
                        color=QColor(0, 220, 140, mic_alpha),
                        fade_color=QColor(0, 220, 140, 20))

        # Core dot — green
        dot_r = (4 + 3 * pulse + 2 * mic) * k
        p.setBrush(QBrush(QColor(0, int(210 + 30 * pulse), int(150 + 30 * pulse))))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

    # ── Ring helper ─────────────────────────────────────────────────

    @staticmethod
    def _draw_ring(painter: QPainter, cx: float, cy: float,
                   radius: float, angle: float, arc_span: int,
                   width: float, color: QColor, fade_color: QColor):
        """Draw a single arc ring with a faded tail."""
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, int(angle * 16), int(arc_span * 16))
        # Faded tail
        pen2 = QPen(fade_color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawArc(rect, int((angle + arc_span) * 16),
                        int((360 - arc_span) * 16))
