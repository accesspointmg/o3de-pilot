# O3DE Pilot GUI - Splash / Loading Screen
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Animated splash screen shown during application startup.

Displays a spinner, status text, and progress while the main
window loads manifests, resolves objects, and fetches remotes.
"""

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QConicalGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication


class SpinnerWidget(QWidget):
    """Animated circular spinner."""

    def __init__(self, size: int = 48, parent=None):
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)  # ~60 fps

    def _rotate(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw arc with gradient tail
        pen = QPen(QColor("#0078D4"), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        margin = 4
        rect = QRectF(margin, margin, self._size - 2 * margin, self._size - 2 * margin)
        # Draw a 270° arc starting from the current angle
        painter.drawArc(rect, int(self._angle * 16), int(270 * 16))

        # Draw a faded tail for the remaining 90°
        fade_pen = QPen(QColor(0, 120, 212, 60), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(fade_pen)
        painter.drawArc(rect, int((self._angle + 270) * 16), int(90 * 16))

        painter.end()

    def stop(self):
        self._timer.stop()


class SplashScreen(QWidget):
    """
    Loading screen shown while the application initialises.

    Usage::

        splash = SplashScreen()
        splash.show()
        splash.set_status("Resolving manifest...")
        # ... do work ...
        splash.set_status("Fetching remote repos...")
        # ... do work ...
        splash.finish()  # hides and deletes
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 260)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Card container
        card = QWidget()
        card.setObjectName("splashCard")
        card.setStyleSheet("""
            #splashCard {
                background-color: #1E1E1E;
                border: 1px solid #333333;
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 28)
        card_layout.setSpacing(16)

        # Title
        title = QLabel("O3DE Pilot")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #EEEEEE; font-size: 22px; font-weight: bold; background: transparent;")
        card_layout.addWidget(title)

        # Spinner (centred)
        spinner_container = QWidget()
        spinner_container.setStyleSheet("background: transparent;")
        spinner_layout = QVBoxLayout(spinner_container)
        spinner_layout.setContentsMargins(0, 0, 0, 0)
        spinner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spinner = SpinnerWidget(48, spinner_container)
        spinner_layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(spinner_container)

        # Status text
        self._status = QLabel("Initialising...")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #999999; font-size: 12px; background: transparent;")
        card_layout.addWidget(self._status)

        # Detail text (smaller, dimmer — e.g. object count)
        self._detail = QLabel("")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        card_layout.addWidget(self._detail)

        layout.addWidget(card)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_status(self, text: str, detail: str = ""):
        """Update the status message (and optional detail line)."""
        self._status.setText(text)
        self._detail.setText(detail)
        QApplication.processEvents()

    def finish(self):
        """Stop the spinner, hide, and schedule deletion."""
        self._spinner.stop()
        self.hide()
        self.deleteLater()

    # ------------------------------------------------------------------
    # Centre on screen
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
