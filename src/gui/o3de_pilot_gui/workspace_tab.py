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
    QLabel, QFrame, QPushButton, QFileDialog, QMenu, QApplication,
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
        self._file_links: dict[str, str] = {}   # source_abs_posix → dest_rel_posix
        self._source_paths: dict[str, str] = {}  # owner name → root path
        self._ws_path: str = ""  # current workspace directory path
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
        self._tree.setHeaderLabels(["Name", "Source", "Destination"])
        self._tree.setRootIsDecorated(True)
        self._tree.setColumnWidth(0, 280)
        self._tree.setColumnWidth(1, 350)
        self._tree.setColumnWidth(2, 350)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)
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

    def refresh(self) -> None:
        """Clear and rescan workspaces (call after creating/deleting a workspace)."""
        self._ws_list.clear()
        self._tree.clear()
        self._clear_legend()
        self._scan_workspaces()

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
                "file_links": {
                    "/src/engine/engine.json": "Engines/o3de/engine.json",
                    "/src/engine/Code/main.cpp": "Engines/o3de/Code/main.cpp",
                    "/src/engine/Code/init.cpp": "Engines/o3de/Code/init.cpp",
                    "/src/gems/Atom/gem.json": "Gems/Atom/gem.json",
                    "/src/gems/Atom/Code/render.cpp": "Gems/Atom/Code/render.cpp",
                    "/src/gems/PhysX/gem.json": "Gems/PhysX/gem.json",
                    "/src/gems/PhysX/Code/physics.cpp": "Gems/PhysX/Code/physics.cpp",
                    "/src/projects/demo/project.json": "Projects/demo/project.json",
                    "/src/projects/demo/Assets/level.prefab": "Projects/demo/Assets/level.prefab",
                },
                "sources": {
                    "/src/engine": "org.o3de.engine.o3de",
                    "/src/gems/Atom": "org.o3de.gem.atom",
                    "/src/gems/PhysX": "org.o3de.gem.physx",
                    "/src/projects/demo": "com.example.project.demo",
                },
            },
            {
                "name": "test-workspace",
                "path": "/tmp/workspaces/test-workspace",
                "file_links": {
                    "/src/engine/engine.json": "Engines/o3de/engine.json",
                    "/src/projects/alpha/project.json": "Projects/alpha/project.json",
                    "/src/overlays/console/overlay.json": "Overlays/console/overlay.json",
                },
                "sources": {
                    "/src/engine": "org.o3de.engine.o3de",
                    "/src/projects/alpha": "com.test.project.alpha",
                    "/src/overlays/console": "com.test.overlay.console",
                },
            },
        ]

        for ws in demo_workspaces:
            item = QListWidgetItem(ws["name"])
            item.setData(Qt.ItemDataRole.UserRole, ws["path"])
            item.setData(Qt.ItemDataRole.UserRole + 1, ws["file_links"])
            # Store sources as path→name (inverted from the new schema)
            item.setData(Qt.ItemDataRole.UserRole + 2, ws.get("sources", {}))
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
        self._ws_path = ws_path or ""

        # Try to load file_links from item data (demo) or from disk
        links = current.data(Qt.ItemDataRole.UserRole + 1)
        if links and isinstance(links, dict):
            self._file_links = links
            # Demo sources stored as path→name
            demo_sources = current.data(Qt.ItemDataRole.UserRole + 2)
            if demo_sources and isinstance(demo_sources, dict):
                self._source_paths = {v: k for k, v in demo_sources.items()}
        else:
            self._file_links = self._load_file_links(ws_path)

        # Derive owner names from source paths
        unique_owners = sorted(set(self._source_paths.keys()))
        self._colors = _assign_colors(unique_owners)
        self._build_legend(unique_owners)

        if self._file_links:
            self._build_tree_from_links()
        else:
            self._start_tree_load(ws_path)

    def _load_file_links(self, ws_path_str: str) -> dict[str, str]:
        """Load file_links from workspace metadata on disk."""
        try:
            ws_path = Path(ws_path_str)
            from o3de_cli.commands.workspace import _read_workspace_meta
            meta = _read_workspace_meta(ws_path)
            if meta is not None:
                # Build name → path lookup from categorised sources
                self._source_paths = {}
                for type_dict in [meta.sources.engines, meta.sources.projects,
                                  meta.sources.gems, meta.sources.templates,
                                  meta.sources.overlays]:
                    self._source_paths.update(type_dict)
                return dict(meta.file_links)
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
            path = self._source_paths.get(name, "")
            display = f"{name}  ({path})" if path else name
            label = QLabel(display)
            label.setStyleSheet("color: #CCCCCC; font-size: 11px;")
            self._legend_layout.addWidget(swatch)
            self._legend_layout.addWidget(label)
        self._legend_layout.addStretch()

    # ── Tree building ───────────────────────────────────────────────

    def _owner_for_source(self, source_path: str) -> str:
        """Determine owner name by matching source path against source roots."""
        norm = source_path.replace("\\", "/").rstrip("/")
        best_name = ""
        best_len = 0
        for name, root in self._source_paths.items():
            root_norm = root.replace("\\", "/").rstrip("/")
            if (norm.startswith(root_norm + "/") or norm == root_norm) and len(root_norm) > best_len:
                best_name = name
                best_len = len(root_norm)
        return best_name

    def _build_tree_from_links(self) -> None:
        """Build a tree from file_links (source → dest_rel)."""
        self._tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}

        # Invert: dest_rel → source_abs
        dest_to_source: dict[str, str] = {v: k for k, v in self._file_links.items()}

        for dest_rel in sorted(dest_to_source):
            parts = dest_rel.split("/")
            for i in range(len(parts)):
                partial = "/".join(parts[: i + 1])
                if partial in nodes:
                    continue
                item = QTreeWidgetItem()
                item.setText(0, parts[i])
                is_leaf = i == len(parts) - 1
                if is_leaf:
                    source_abs = dest_to_source[dest_rel]
                    owner = self._owner_for_source(source_abs)
                    color = self._colors.get(owner)
                    if color:
                        item.setForeground(0, QBrush(color))
                        item.setForeground(1, QBrush(QColor("#555555")))
                        item.setForeground(2, QBrush(QColor("#555555")))
                    item.setText(1, source_abs)
                    item.setToolTip(1, source_abs)
                    if self._ws_path:
                        dest_full = str(Path(self._ws_path) / dest_rel)
                        item.setText(2, dest_full)
                        item.setToolTip(2, dest_full)
                parent_path = "/".join(parts[:i]) if i > 0 else ""
                if parent_path and parent_path in nodes:
                    nodes[parent_path].addChild(item)
                else:
                    self._tree.addTopLevelItem(item)
                nodes[partial] = item

        self._tree.expandToDepth(2)

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
                # Try to find owner from resolved symlink
                abs_path = ws_root / rel_path.replace("/", os.sep)
                source = self._resolve_link(abs_path)
                if source:
                    owner = self._owner_for_source(source)
                else:
                    owner = ""
                color = self._colors.get(owner)
                if color:
                    item.setForeground(0, QBrush(color))
                    item.setForeground(1, QBrush(QColor("#555555")))
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

    def _on_tree_context_menu(self, pos) -> None:
        """Show right-click menu with copy options for Name/Source/Destination."""
        item = self._tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #252526; color: #CCCCCC; border: 1px solid #454545; }"
            "QMenu::item:selected { background-color: #094771; }"
        )
        name = item.text(0)
        source = item.text(1)
        destination = item.text(2)

        if name:
            act = menu.addAction("Copy Name")
            act.triggered.connect(lambda _=False, t=name: QApplication.clipboard().setText(t))
        if source:
            act = menu.addAction("Copy Source Path")
            act.triggered.connect(lambda _=False, t=source: QApplication.clipboard().setText(t))
        if destination:
            act = menu.addAction("Copy Destination Path")
            act.triggered.connect(lambda _=False, t=destination: QApplication.clipboard().setText(t))

        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(pos))
