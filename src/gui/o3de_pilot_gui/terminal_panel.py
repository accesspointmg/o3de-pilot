# O3DE Pilot GUI — Terminal Panel (Dockable)
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Dockable terminal panel providing a full PTY-backed terminal.

Uses xterm.js in a QWebEngineView for rendering and pywinpty (Windows)
or the pty module (Unix) for the shell backend. Communication between
the JS terminal and the Python PTY is done via QWebChannel.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QUrl, Signal, Slot, QTimer
from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel


# ── PTY Bridge (exposed to JS via QWebChannel) ────────────────────────────

class PtyBridge(QObject):
    """Bridge between xterm.js (frontend) and the PTY process (backend).

    Exposed to JavaScript as `window.ptyBridge`.
    """

    # Signal emitted when PTY has output to send to xterm.js
    output_ready = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pty = None
        self._reader_thread: threading.Thread | None = None
        self._running = False

    def start_shell(self, cwd: str | None = None, venv: str | None = None,
                    cols: int = 80, rows: int = 24) -> None:
        """Start the shell process in the PTY."""
        if self._running:
            return

        self._running = True
        self._venv = venv

        if sys.platform == "win32":
            self._start_windows_pty(cwd, cols, rows)
        else:
            self._start_unix_pty(cwd, cols, rows)

    def _start_windows_pty(self, cwd: str | None, cols: int, rows: int) -> None:
        """Start a ConPTY shell on Windows using winpty."""
        from winpty import PtyProcess

        # Prefer PowerShell 7 > PowerShell 5.1 > COMSPEC
        ps7_path = r"C:\Program Files\PowerShell\7\pwsh.exe"
        ps5_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        if os.path.exists(ps7_path):
            shell = ps7_path
        elif os.path.exists(ps5_path):
            shell = ps5_path
        else:
            shell = os.environ.get("COMSPEC", "powershell.exe")

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        # Activate venv by prepending Scripts to PATH
        if self._venv:
            scripts_dir = os.path.join(self._venv, "Scripts")
            env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = self._venv

        self._pty = PtyProcess.spawn(
            [shell],
            dimensions=(rows, cols),
            cwd=cwd,
            env=env,
        )

        # Reader thread: read PTY output and emit signal
        self._reader_thread = threading.Thread(
            target=self._read_pty_output, daemon=True
        )
        self._reader_thread.start()

    def _start_unix_pty(self, cwd: str | None, cols: int, rows: int) -> None:
        """Start a PTY shell on Unix."""
        import pty
        import struct
        import fcntl
        import termios
        import subprocess

        shell = os.environ.get("SHELL", "/bin/bash")

        # Create PTY
        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd

        # Set initial size on the PTY
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        # Activate venv by prepending bin to PATH
        if self._venv:
            bin_dir = os.path.join(self._venv, "bin")
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = self._venv

        self._process = subprocess.Popen(
            [shell],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            preexec_fn=os.setsid,
        )
        os.close(slave_fd)

        self._reader_thread = threading.Thread(
            target=self._read_unix_output, daemon=True
        )
        self._reader_thread.start()

    def _read_pty_output(self) -> None:
        """Read from Windows PTY in a loop."""
        try:
            while self._running and self._pty is not None and self._pty.isalive():
                try:
                    data = self._pty.read(4096)
                    if data:
                        self.output_ready.emit(data)
                except EOFError:
                    break
                except Exception:
                    break
        finally:
            self._running = False

    def _read_unix_output(self) -> None:
        """Read from Unix PTY master fd in a loop."""
        try:
            while self._running:
                try:
                    data = os.read(self._master_fd, 4096)
                    if data:
                        self.output_ready.emit(data.decode("utf-8", errors="replace"))
                    else:
                        break
                except OSError:
                    break
        finally:
            self._running = False

    @Slot(str)
    def onTerminalInput(self, data: str) -> None:
        """Receive keyboard input from xterm.js and write to PTY."""
        if not self._running:
            return

        if sys.platform == "win32":
            if self._pty is not None and self._pty.isalive():
                self._pty.write(data)
        else:
            if hasattr(self, "_master_fd"):
                os.write(self._master_fd, data.encode("utf-8"))

    @Slot(int, int)
    def onTerminalResize(self, cols: int, rows: int) -> None:
        """Receive resize events from xterm.js and resize the PTY."""
        if not self._running:
            return
        # Ignore unreasonable sizes from early layout
        if cols < 10 or rows < 2:
            return

        if sys.platform == "win32":
            if self._pty is not None and self._pty.isalive():
                self._pty.setwinsize(rows, cols)
        else:
            if hasattr(self, "_master_fd"):
                import struct
                import fcntl
                import termios
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def stop(self) -> None:
        """Stop the PTY process and reader thread."""
        self._running = False
        if sys.platform == "win32":
            if self._pty is not None and self._pty.isalive():
                self._pty.close()
        else:
            if hasattr(self, "_process"):
                self._process.terminate()
            if hasattr(self, "_master_fd"):
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass

    def write_command(self, command: str) -> None:
        """Write a command to the PTY (used for programmatic execution)."""
        self.onTerminalInput(command + "\r")


# ── Terminal Panel ─────────────────────────────────────────────────────────

class TerminalPanel(QDockWidget):
    """Dockable terminal panel with a full PTY shell."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Terminal", parent)
        self.setObjectName("TerminalPanel")
        self.setMinimumHeight(150)
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Main container
        container = QWidget()
        container.setAutoFillBackground(True)
        container.setStyleSheet("background-color: #1E1E1E;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # WebEngine view for xterm.js
        self._web_view = QWebEngineView()
        self._web_view.setStyleSheet("background-color: #1E1E1E;")
        layout.addWidget(self._web_view)

        self.setWidget(container)

        # PTY bridge
        self._bridge = PtyBridge(self)
        self._bridge.output_ready.connect(self._on_pty_output)

        # Web channel for JS ↔ Python communication
        self._channel = QWebChannel(self._web_view.page())
        self._channel.registerObject("ptyBridge", self._bridge)
        self._web_view.page().setWebChannel(self._channel)

        # Load the terminal HTML
        html_path = Path(__file__).parent / "terminal" / "terminal.html"
        self._web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

        # Once loaded, start the shell
        self._web_view.loadFinished.connect(self._on_page_loaded)

        # Track if shell started and JS is ready
        self._shell_started = False
        self._js_ready = False
        self._output_buffer: list[str] = []

    def _on_page_loaded(self, ok: bool) -> None:
        """Page loaded — wait for layout before starting shell."""
        if ok and not self._shell_started:
            self._shell_started = True
            # Delay to let Qt finish laying out the dock widget
            QTimer.singleShot(500, self._inject_webchannel)

    def _inject_webchannel(self) -> None:
        """Inject the QWebChannel JS and wire up the bridge."""
        js = """
        new QWebChannel(qt.webChannelTransport, function(channel) {
            window.ptyBridge = channel.objects.ptyBridge;
        });
        """
        self._web_view.page().runJavaScript(js, self._on_channel_ready)

    def _on_channel_ready(self, result) -> None:
        """Channel is ready — fit terminal then start shell with correct size."""
        self._js_ready = True
        # Flush any buffered output
        if self._output_buffer:
            for data in self._output_buffer:
                self._write_to_js(data)
            self._output_buffer.clear()
        # Fit terminal to container, get size, then start shell with those dims
        QTimer.singleShot(300, self._fit_and_start_shell)

    def _fit_and_start_shell(self) -> None:
        """Calculate size from widget, set xterm.js and start shell."""
        # Calculate cols/rows from actual widget pixel dimensions
        # Font size 13 → approx 8.4px per char width, 17px per line height
        width = self._web_view.width()
        height = self._web_view.height()
        cols = max(80, int(width / 8.4))
        rows = max(24, int(height / 17))

        # Resize xterm.js to match, then start shell
        js = f"term.resize({cols}, {rows});"
        self._web_view.page().runJavaScript(js)

        project_dir = Path(__file__).resolve().parents[3]  # o3de-pilot root
        cwd = str(project_dir)
        venv = str(project_dir / ".venv")
        self._bridge.start_shell(cwd, venv, cols, rows)

    def _on_pty_output(self, data: str) -> None:
        """Receive PTY output and send it to xterm.js."""
        if not self._js_ready:
            self._output_buffer.append(data)
            return
        self._write_to_js(data)

    def _write_to_js(self, data: str) -> None:
        """Send data to xterm.js via runJavaScript using base64 to avoid escaping issues."""
        import base64
        encoded = base64.b64encode(data.encode("utf-8")).decode("ascii")
        self._web_view.page().runJavaScript(
            f"window.writeToTerminal(atob('{encoded}'));"
        )

    def execute_command(self, command: str) -> None:
        """Execute a command in the terminal (programmatic use)."""
        if self._shell_started and self._bridge._running:
            self._bridge.write_command(command)

    def closeEvent(self, event) -> None:
        """Clean up PTY on close."""
        self._bridge.stop()
        super().closeEvent(event)

    def stop(self) -> None:
        """Stop the terminal (called from MainWindow closeEvent)."""
        self._bridge.stop()
