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



@pytest.fixture
def fake_terminal(qtbot, monkeypatch):
    """A panel whose shell and page loading are stand-ins: records shell starts
    and commands, and 'loads' the page instantly instead of using WebEngine."""
    panel = TerminalPanel()
    qtbot.addWidget(panel)
    calls = {"starts": 0, "commands": []}

    def start_shell(*args, **kwargs):
        calls["starts"] += 1
        panel._bridge._running = True

    monkeypatch.setattr(panel._bridge, "start_shell", start_shell)
    monkeypatch.setattr(panel._bridge, "write_command", lambda c: calls["commands"].append(c))
    monkeypatch.setattr(panel._bridge, "stop", lambda: setattr(panel._bridge, "_running", False))
    monkeypatch.setattr(panel._web_view, "reload", lambda: panel._on_page_loaded(True))
    monkeypatch.setattr(panel, "_inject_webchannel",
                        lambda gen=None: panel._on_channel_ready(None, gen))
    return panel, calls


def test_reopening_a_closed_dock_starts_a_new_shell(qtbot, fake_terminal):
    panel, calls = fake_terminal
    panel.show()
    panel._on_page_loaded(True)
    qtbot.waitUntil(lambda: calls["starts"] == 1, timeout=3000)

    panel.close()                       # the dock's X
    assert not panel._bridge._running
    panel.show()                        # View > Terminal
    qtbot.waitUntil(lambda: calls["starts"] == 2, timeout=3000)
    assert panel._bridge._running


def test_commands_sent_without_a_shell_run_when_it_starts(qtbot, fake_terminal):
    panel, calls = fake_terminal
    panel.show()
    panel.close()
    panel.execute_command("o3de unregister /tmp/x")   # what MainWindow does...
    panel.show()                                     # ...followed by show()
    qtbot.waitUntil(lambda: calls["commands"] == ["o3de unregister /tmp/x"], timeout=3000)


def test_after_app_shutdown_nothing_restarts(qtbot, fake_terminal):
    panel, calls = fake_terminal
    panel.stop()                        # MainWindow is closing
    panel.execute_command("echo late")
    panel.show()
    qtbot.wait(1000)
    assert calls["starts"] == 0 and calls["commands"] == []



def test_a_shell_that_exited_restarts_when_a_command_is_sent(qtbot, fake_terminal):
    panel, calls = fake_terminal
    panel.show()
    panel._on_page_loaded(True)
    qtbot.waitUntil(lambda: calls["starts"] == 1, timeout=3000)
    panel._bridge._running = False      # the user typed `exit`
    panel.execute_command("o3de list projects")
    assert calls["starts"] == 2
    assert calls["commands"] == ["o3de list projects"]


def test_old_startup_callbacks_are_ignored_after_reopening(qtbot, fake_terminal):
    """A timer or JavaScript reply from before close/reopen must not start the
    shell on the reloaded page before that page is ready."""
    panel, calls = fake_terminal
    panel.show()
    old_gen = panel._startup_gen
    panel.close()
    panel.show()                        # reload: new startup takes ~800 ms
    panel._on_channel_ready(None, old_gen)    # late reply from the old page
    panel._fit_and_start_shell(old_gen)       # late timer from the old page
    assert calls["starts"] == 0
    qtbot.waitUntil(lambda: calls["starts"] == 1, timeout=3000)
    qtbot.wait(500)
    assert calls["starts"] == 1



@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="counts PTYs via /proc")
def test_restarting_an_exited_shell_does_not_leak_ptys(qtbot, monkeypatch):
    """A real shell: let it exit on its own, start another, then stop. Each
    step must leave at most one PTY open (the current shell's)."""
    import os
    from o3de_pilot_gui.terminal_panel import PtyBridge

    def open_ptys():
        n = 0
        for fd in os.listdir("/proc/self/fd"):
            try:
                if os.readlink(f"/proc/self/fd/{fd}") == "/dev/ptmx":
                    n += 1
            except OSError:
                pass
        return n

    monkeypatch.setenv("SHELL", "/bin/sh")
    before = open_ptys()
    bridge = PtyBridge()
    bridge.start_shell()
    assert open_ptys() == before + 1
    bridge.write_command("exit")
    qtbot.waitUntil(lambda: not bridge._running, timeout=5000)   # exited by itself
    bridge.start_shell()
    assert open_ptys() == before + 1
    bridge.stop()
    assert open_ptys() == before
    bridge.stop()                       # second stop: no double close, no error
