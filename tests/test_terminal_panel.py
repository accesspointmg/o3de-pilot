# O3DE Pilot - Terminal panel lifecycle tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""The terminal panel schedules work on timers (inject the web channel, then
fit xterm.js and start a shell). Those must not run after the panel is gone,
and must never start a shell once the panel has been stopped."""

import pytest

pytest.importorskip("PySide6", reason="PySide6 required for GUI tests")

from PySide6.QtCore import QCoreApplication, QEvent

from o3de_pilot_gui.terminal_panel import TerminalPanel


def _delete_now(widget):
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_pending_timers_do_not_fire_after_panel_is_deleted(qtbot):
    panel = TerminalPanel()
    panel._on_page_loaded(True)        # schedules _inject_webchannel (500 ms)
    panel._on_channel_ready(None)      # schedules _fit_and_start_shell (300 ms)
    _delete_now(panel)
    # pytest-qt fails the test if a callback raises inside the Qt event loop.
    qtbot.wait(800)


def test_stopped_panel_never_starts_a_shell(qtbot):
    panel = TerminalPanel()
    qtbot.addWidget(panel)
    panel.stop()
    panel._fit_and_start_shell()
    assert not panel._bridge._running


def test_late_javascript_reply_after_panel_is_deleted(qtbot):
    """runJavaScript answers asynchronously; the reply can arrive after the
    panel was deleted (closing the window right after it opened)."""
    panel = TerminalPanel()
    _delete_now(panel)
    panel._on_channel_ready(None)      # the late reply
    qtbot.wait(500)


def test_closing_the_dock_before_startup_never_starts_a_shell(qtbot):
    """Closing the dock hides it (no delete), so the panel's objects stay valid;
    a startup timer still pending must not start a shell afterwards."""
    panel = TerminalPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel._on_channel_ready(None)      # schedules _fit_and_start_shell (300 ms)
    panel.close()
    qtbot.wait(600)
    assert not panel._bridge._running
