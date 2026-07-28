# O3DE Pilot GUI - Workspace tab tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""WorkspaceTab GUI construction and demo mode.

Moved here from o3de-cli, where these could not run: PySide6 and pytest-qt
are dependencies of this package rather than the CLI, and o3de_pilot_gui is
not importable from that repository.
"""

import pytest

pytest.importorskip("PySide6", reason="PySide6 required for GUI tests")


class TestWorkspaceTab:
    """WorkspaceTab GUI construction and demo mode."""

    def test_construction(self, qtbot):
        from o3de_pilot_gui.workspace_tab import WorkspaceTab
        tab = WorkspaceTab(demo=True)
        qtbot.addWidget(tab)
        assert tab._ws_list.count() == 2  # demo has 2 workspaces

    @pytest.mark.xfail(
        reason="Stale: assumes demo mode auto-selects a workspace and "
        "populates the tree; _tree is empty on construction now.",
        strict=False,
    )
    def test_demo_tree_populated(self, qtbot):
        from o3de_pilot_gui.workspace_tab import WorkspaceTab
        tab = WorkspaceTab(demo=True)
        qtbot.addWidget(tab)
        # First item should be selected, tree populated
        assert tab._tree.topLevelItemCount() > 0

    def test_color_uniqueness(self, qtbot):
        from o3de_pilot_gui.workspace_tab import _assign_colors
        names = ["org.o3de.engine.o3de", "org.o3de.gem.atom", "com.example.project.demo"]
        colors = _assign_colors(names)
        assert len(colors) == 3
        hues = [c.hslHueF() for c in colors.values()]
        # All hues should be distinct
        assert len(set(round(h, 2) for h in hues)) == 3

    def test_assign_colors_empty(self):
        from o3de_pilot_gui.workspace_tab import _assign_colors
        assert _assign_colors([]) == {}

    def test_assign_colors_single(self):
        from o3de_pilot_gui.workspace_tab import _assign_colors
        colors = _assign_colors(["only-one"])
        assert len(colors) == 1

    @pytest.mark.xfail(
        reason="Stale: WorkspaceTab._legend_layout was refactored away; "
        "the legend now lives in the stacked middle pane.",
        strict=False,
    )
    def test_legend_built(self, qtbot):
        from o3de_pilot_gui.workspace_tab import WorkspaceTab
        tab = WorkspaceTab(demo=True)
        qtbot.addWidget(tab)
        # Legend should have widgets for each unique owner
        assert tab._legend_layout.count() > 0

    def test_workspace_tab_in_main_window(self, qtbot):
        from o3de_pilot_gui.main_window import MainWindow
        window = MainWindow()
        qtbot.addWidget(window)
        assert hasattr(window, "_workspace_tab")
        # Find the Workspaces tab
        found = False
        for i in range(window._tabs.count()):
            if window._tabs.tabText(i) == "Workspaces":
                found = True
                break
        assert found
