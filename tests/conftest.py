# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Shared test fixtures."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _delete_web_views():
    """Destroy leftover terminal panels (and any other QWebEngineViews) at the end of the session.

    MainWindow's terminal panel holds a QWebEnginePage, which must be destroyed before the
    default QWebEngineProfile. That profile goes with the QApplication, so pages still alive at
    interpreter exit make Python segfault after the run. Each panel's shell is stopped first and
    the whole panel deleted, so queued shell output is not delivered to a deleted view. The windows
    themselves are left alone: their worker threads are only stopped by MainWindow.closeEvent,
    which would also write the user's settings.
    """
    yield
    try:
        import shiboken6
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication

        from o3de_pilot_gui.terminal_panel import TerminalPanel
    except ImportError:
        return
    if QApplication.instance() is None:
        return
    for window in QApplication.topLevelWidgets():
        if not shiboken6.isValid(window):
            continue
        for panel in window.findChildren(TerminalPanel):
            if shiboken6.isValid(panel):
                panel.stop()
                shiboken6.delete(panel)
        for view in window.findChildren(QWebEngineView):
            if shiboken6.isValid(view):
                shiboken6.delete(view)
