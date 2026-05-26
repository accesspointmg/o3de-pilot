# O3DE Pilot GUI - Workspace Tab
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Workspace browser tab.

Shows a list of workspaces on the left and a color-coded directory tree
on the right.  Each source object gets a unique color so the user can
see at a glance which object owns each file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QFrame,
)


def _assign_colors(names: list[str]) -> dict[str, QColor]:
    """Assign perceptually-distinct HSL colors to a list of names.

    Hues are evenly spaced around the wheel (saturation=70%, lightness=55%)
    so they remain readable on a dark background.
    """
    if not names:
        return {}
    step = 360.0 / len(names)
    colors: dict[str, QColor] = {}
    for i, name in enumerate(names):
        hue = int(i * step) % 360
        color = QColor.fromHslF(hue / 360.0, 0.70, 0.55)
        colors[name] = color
    return colors


class _TreeLoader(QObject):
    """Background worker that reads workspace directory structure."""

    loaded = Signal(str, list)  # workspace_path, list of (rel_path, is_dir) tuples

    def __init__(self, ws_path: str, max_depth: int = 3):
        super().__init__()
        self._ws_path = ws_path
        self._max_depth = max_depth

    def run(self) -> None:
        entries: list[tuple[str, bool]] = []
        root = Path(self._ws_path)
        if not root.is_dir():
            self.loaded.emit(self._ws_path, entries)
            return
        self._walk(root, root, 0, entries)
        self.loaded.emit(self._ws_path, entries)

    def _walk(
        self, base: Path, current: Path, depth: int,
        out: list[tuple[str, bool]],
    ) -> None:
        if depth >= self._max_depth:
            return
        try:
            children = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except (PermissionError, OSError):
            return
        for child in children:
            if child.name.startswith("."):
                continue
            rel = child.relative_to(base).as_posix()
            is_dir = child.is_dir()
            out.append((rel, is_dir))
            if is_dir:
                self._walk(base, child, depth + 1, out)


class WorkspaceTab(QWidget):
    """Tab that lists workspaces and shows their directory trees."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        demo: bool = False,
    ):
        super().__init__(parent)
        self._demo = demo
        self._colors: dict[str, QColor] = {}
        self._file_owners: dict[str, str] = {}
        self._loader_thread: QThread | None = None
        self._loader_worker: _TreeLoader | None = None

        self._setup_ui()

        if demo:
            self._load_demo()
        else:
            self._scan_workspaces()

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: workspace list
        self._ws_list = QListWidget()
        self._ws_list.currentItemChanged.connect(self._on_workspace_selected)
        splitter.addWidget(self._ws_list)

        # Right: tree + legend
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name"])
        self._tree.setRootIsDecorated(True)
        right_layout.addWidget(self._tree, stretch=1)

        # Color legend
        self._legend_frame = QFrame()
        self._legend_layout = QHBoxLayout(self._legend_frame)
        self._legend_layout.setContentsMargins(4, 2, 4, 2)
        right_layout.addWidget(self._legend_frame)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)  # 30%
        splitter.setStretchFactor(1, 3)  # 70%

        layout.addWidget(splitter)

    # ── Scanning ────────────────────────────────────────────────────

    def _scan_workspaces(self) -> None:
        """Scan the default workspaces directory for workspace.json files."""
        try:
            from o3de_pilot.core import get_default_workspaces_path
            ws_root = get_default_workspaces_path()
        except Exception:
            return

        if not ws_root.is_dir():
            return

        from o3de_pilot.commands.workspace import _find_workspace_meta

        for ws_dir in sorted(ws_root.iterdir()):
            if ws_dir.is_dir() and _find_workspace_meta(ws_dir) is not None:
                item = QListWidgetItem(ws_dir.name)
                item.setData(Qt.ItemDataRole.UserRole, str(ws_dir))
                self._ws_list.addItem(item)

    # ── Demo ────────────────────────────────────────────────────────

    def _load_demo(self) -> None:
        """Populate with synthetic data for --demo mode."""
        demo_workspaces = [
            {
                "name": "my-build",
                "path": "/tmp/workspaces/my-build",
                "file_owners": {
                    "engine.json": "org.o3de.engine.o3de",
                    "Code/main.cpp": "org.o3de.engine.o3de",
                    "Code/init.cpp": "org.o3de.engine.o3de",
                    "Gems/Atom/gem.json": "org.o3de.gem.atom",
                    "Gems/Atom/Code/render.cpp": "org.o3de.gem.atom",
                    "Gems/PhysX/gem.json": "org.o3de.gem.physx",
                    "Gems/PhysX/Code/physics.cpp": "org.o3de.gem.physx",
                    "project.json": "com.example.project.demo",
                    "Assets/level.prefab": "com.example.project.demo",
                },
            },
            {
                "name": "test-workspace",
                "path": "/tmp/workspaces/test-workspace",
                "file_owners": {
                    "engine.json": "org.o3de.engine.o3de",
                    "project.json": "com.test.project.alpha",
                    "overlay.json": "com.test.overlay.console",
                },
            },
        ]

        for ws in demo_workspaces:
            item = QListWidgetItem(ws["name"])
            item.setData(Qt.ItemDataRole.UserRole, ws["path"])
            item.setData(Qt.ItemDataRole.UserRole + 1, ws["file_owners"])
            self._ws_list.addItem(item)

        if self._ws_list.count():
            self._ws_list.setCurrentRow(0)

    # ── Selection ───────────────────────────────────────────────────

    def _on_workspace_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._tree.clear()
        self._clear_legend()

        if current is None:
            return

        ws_path = current.data(Qt.ItemDataRole.UserRole)

        # Try to load file_owners from item data (demo) or from disk
        owners = current.data(Qt.ItemDataRole.UserRole + 1)
        if owners and isinstance(owners, dict):
            self._file_owners = owners
        else:
            self._file_owners = self._load_file_owners(ws_path)

        # Assign colors from unique owner names
        unique_owners = sorted(set(self._file_owners.values()))
        self._colors = _assign_colors(unique_owners)
        self._build_legend(unique_owners)

        if self._demo:
            # Build tree directly from file_owners keys
            self._build_tree_from_owners()
        else:
            self._start_tree_load(ws_path)

    def _load_file_owners(self, ws_path_str: str) -> dict[str, str]:
        """Load file_owners from workspace metadata on disk."""
        ws_path = Path(ws_path_str)
        from o3de_pilot.commands.workspace import _read_workspace_meta
        meta = _read_workspace_meta(ws_path)
        if meta is not None:
            return dict(meta.file_owners)
        return {}

    # ── Legend ──────────────────────────────────────────────────────

    def _clear_legend(self) -> None:
        while self._legend_layout.count():
            child = self._legend_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _build_legend(self, names: list[str]) -> None:
        self._clear_legend()
        for name in names:
            color = self._colors.get(name, QColor(180, 180, 180))
            swatch = QLabel("■")
            swatch.setStyleSheet(f"color: {color.name()}; font-size: 14px;")
            label = QLabel(name)
            label.setStyleSheet("color: #CCCCCC; font-size: 11px;")
            self._legend_layout.addWidget(swatch)
            self._legend_layout.addWidget(label)
        self._legend_layout.addStretch()

    # ── Tree building ───────────────────────────────────────────────

    def _build_tree_from_owners(self) -> None:
        """Build a tree purely from file_owners keys (demo mode)."""
        self._tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}

        for rel_path in sorted(self._file_owners):
            parts = rel_path.split("/")
            for i in range(len(parts)):
                partial = "/".join(parts[: i + 1])
                if partial in nodes:
                    continue
                item = QTreeWidgetItem()
                item.setText(0, parts[i])
                is_leaf = i == len(parts) - 1
                if is_leaf:
                    owner = self._file_owners.get(rel_path, "")
                    color = self._colors.get(owner)
                    if color:
                        item.setForeground(0, QBrush(color))
                parent_path = "/".join(parts[:i]) if i > 0 else ""
                if parent_path and parent_path in nodes:
                    nodes[parent_path].addChild(item)
                else:
                    self._tree.addTopLevelItem(item)
                nodes[partial] = item

        self._tree.expandAll()

    def _start_tree_load(self, ws_path: str) -> None:
        """Load directory tree in background thread."""
        # Clean up previous
        if self._loader_thread is not None:
            self._loader_thread.quit()
            self._loader_thread.wait()

        self._loader_thread = QThread()
        self._loader_worker = _TreeLoader(ws_path)
        self._loader_worker.moveToThread(self._loader_thread)
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.loaded.connect(self._on_tree_loaded)
        self._loader_worker.loaded.connect(self._loader_thread.quit)
        self._loader_thread.start()

    def _on_tree_loaded(self, ws_path: str, entries: list[tuple[str, bool]]) -> None:
        """Populate tree widget from loaded entries."""
        self._tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}

        for rel_path, is_dir in entries:
            parts = rel_path.split("/")
            name = parts[-1]
            parent_path = "/".join(parts[:-1])

            item = QTreeWidgetItem()
            item.setText(0, name)

            if not is_dir:
                owner = self._file_owners.get(rel_path, "")
                color = self._colors.get(owner)
                if color:
                    item.setForeground(0, QBrush(color))

            if parent_path in nodes:
                nodes[parent_path].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            nodes[rel_path] = item

        self._tree.expandToDepth(1)
