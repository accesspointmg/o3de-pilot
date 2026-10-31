# O3DE Pilot - shared test fixtures
# SPDX-License-Identifier: Apache-2.0 OR MIT

import pytest


@pytest.fixture(scope="session", autouse=True)
def _delete_qt_widgets_at_exit():
    """Delete leftover Qt widgets before Python shuts down.

    The terminal panel holds a QWebEngineView. If the QApplication (and with
    it the WebEngine profile) is destroyed first, Python segfaults at exit and
    the test run reports failure even when every test passed.
    """
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
