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
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QFrame, QPushButton, QFileDialog,
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

    _DARK_STYLE = """
        QListWidget, QTreeWidget {
            background-color: #1E1E1E;
            color: #CCCCCC;
            border: 1px solid #333333;
            font-size: 10pt;
        }
        QListWidget::item:selected, QTreeWidget::item:selected {
            background-color: #094771;
            color: #EEEEEE;
        }
        QListWidget::item:hover, QTreeWidget::item:hover {
            background-color: #2A2D2E;
        }
        QHeaderView::section {
            background-color: #252526;
            color: #CCCCCC;
            border: none;
            padding: 4px 8px;
            font-size: 9pt;
        }
        QSplitter::handle {
            background-color: #333333;
            width: 2px;
        }
        QPushButton {
            background-color: #0E639C;
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            padding: 5px 12px;
            font-size: 9pt;
        }
        QPushButton:hover {
            background-color: #1177BB;
        }
        QPushButton:pressed {
            background-color: #094771;
        }
        QFrame {
            background-color: #1E1E1E;
            border: none;
        }
    """

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet(self._DARK_STYLE)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane: workspace list + open button
        left = QWidget()
        left.setStyleSheet("background-color: #1E1E1E;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self._ws_list = QListWidget()
        self._ws_list.currentItemChanged.connect(self._on_workspace_selected)
        left_layout.addWidget(self._ws_list, stretch=1)

        open_btn = QPushButton("Open Workspace...")
        open_btn.clicked.connect(self._on_open_workspace)
        left_layout.addWidget(open_btn)

        # Placeholder label shown when list is empty
        self._empty_label = QLabel("No workspaces found. Click Open Workspace below.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666666; font-size: 9pt; padding: 20px;")
        left_layout.addWidget(self._empty_label)

        splitter.addWidget(left)

        # Right pane: tree + legend
        right = QWidget()
        right.setStyleSheet("background-color: #1E1E1E;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Source"])
        self._tree.setRootIsDecorated(True)
        self._tree.setColumnWidth(0, 280)
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
        """Scan the default workspaces directory and manifest for workspaces."""
        from o3de_cli.commands.workspace import (
            _find_workspace_meta, _get_registered_workspaces,
        )

        seen: set[str] = set()

        # Default workspaces folder
        try:
            from o3de_cli.core import get_default_workspaces_path
            ws_root = get_default_workspaces_path()
            if ws_root.is_dir():
                for ws_dir in sorted(ws_root.iterdir()):
                    if ws_dir.is_dir() and _find_workspace_meta(ws_dir) is not None:
                        resolved = str(ws_dir.resolve())
                        if resolved not in seen:
                            seen.add(resolved)
                            item = QListWidgetItem(ws_dir.name)
                            item.setData(Qt.ItemDataRole.UserRole, str(ws_dir))
                            self._ws_list.addItem(item)
        except Exception:
            pass

        # Manifest-registered workspaces
        try:
            for ws_dir in _get_registered_workspaces():
                if ws_dir.is_dir() and _find_workspace_meta(ws_dir) is not None:
                    resolved = str(ws_dir.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        item = QListWidgetItem(ws_dir.name)
                        item.setData(Qt.ItemDataRole.UserRole, str(ws_dir))
                        self._ws_list.addItem(item)
        except Exception:
            pass

        self._update_empty_label()

    def _on_open_workspace(self) -> None:
        """Open a workspace from an arbitrary directory."""
        path = QFileDialog.getExistingDirectory(
            self, "Open Workspace Directory", "",
        )
        if not path:
            return
        ws_path = Path(path)
        # Check for duplicates
        for i in range(self._ws_list.count()):
            if self._ws_list.item(i).data(Qt.ItemDataRole.UserRole) == str(ws_path):
                self._ws_list.setCurrentRow(i)
                return
        item = QListWidgetItem(ws_path.name)
        item.setData(Qt.ItemDataRole.UserRole, str(ws_path))
        self._ws_list.addItem(item)
        self._ws_list.setCurrentItem(item)
        self._update_empty_label()

    def _update_empty_label(self) -> None:
        """Show/hide the empty placeholder based on list count."""
        self._empty_label.setVisible(self._ws_list.count() == 0)

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
        self._update_empty_label()

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
        try:
            ws_path = Path(ws_path_str)
            from o3de_cli.commands.workspace import _read_workspace_meta
            meta = _read_workspace_meta(ws_path)
            if meta is not None:
                return dict(meta.file_owners)
        except Exception:
            pass
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
        ws_root = Path(ws_path)

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
                    item.setForeground(1, QBrush(QColor("#555555")))

                # Resolve symlink target
                abs_path = ws_root / rel_path.replace("/", os.sep)
                source = self._resolve_link(abs_path)
                if source:
                    item.setText(1, source)
                    item.setToolTip(0, source)

            if parent_path in nodes:
                nodes[parent_path].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            nodes[rel_path] = item

        if not entries:
            placeholder = QTreeWidgetItem()
            placeholder.setText(0, "(empty workspace -- no files found)")
            placeholder.setForeground(0, QBrush(QColor("#666666")))
            self._tree.addTopLevelItem(placeholder)
        else:
            self._tree.expandToDepth(1)

    @staticmethod
    def _resolve_link(path: Path) -> str:
        """Return the real source path if *path* is a symlink, else ''."""
        try:
            if path.is_symlink():
                return str(path.resolve())
        except (OSError, ValueError):
            pass
        return ""
