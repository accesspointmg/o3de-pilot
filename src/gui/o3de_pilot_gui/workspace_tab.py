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
import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject, QUrl, QMimeData
from PySide6.QtGui import QColor, QBrush, QFont, QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QStackedWidget,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QFrame, QPushButton, QFileDialog, QMenu, QApplication,
    QStyle, QSizePolicy, QComboBox, QMessageBox,
)

from .command_specs import get_commands_for_group

logger = logging.getLogger("o3de_pilot_gui.workspace_tab")


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
    """Background worker that reads a single directory level.

    Emits (ws_path, parent_rel, entries) where entries is a list of
    (name, is_dir, source) tuples for immediate children.
    """

    loaded = Signal(str, str, list)  # ws_path, parent_rel, entries

    def __init__(self, ws_path: str, parent_rel: str, file_links: dict | None = None):
        super().__init__()
        self._ws_path = ws_path
        self._parent_rel = parent_rel
        # Reverse lookup: dest_rel → source_abs
        self._dest_to_source: dict[str, str] = (
            {v: k for k, v in file_links.items()} if file_links else {}
        )

    def run(self) -> None:
        entries: list[tuple[str, bool, str]] = []
        root = Path(self._ws_path)
        target = root / self._parent_rel if self._parent_rel else root
        if not target.is_dir():
            self.loaded.emit(self._ws_path, self._parent_rel, entries)
            return
        try:
            children = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        except (PermissionError, OSError):
            self.loaded.emit(self._ws_path, self._parent_rel, entries)
            return
        for child in children:
            if child.name.startswith("."):
                continue
            is_dir = child.is_dir()
            source = ""
            if not is_dir:
                rel = child.relative_to(root).as_posix()
                source = self._dest_to_source.get(rel, "")
                if not source:
                    source = self._resolve_link(child)
            entries.append((child.name, is_dir, source))
        self.loaded.emit(self._ws_path, self._parent_rel, entries)

    @staticmethod
    def _resolve_link(path: Path) -> str:
        """Return the real source path if *path* is a symlink, else ''."""
        try:
            if path.is_symlink():
                return str(path.resolve())
        except (OSError, ValueError):
            pass
        return ""


class _DragTreeWidget(QTreeWidget):
    """QTreeWidget that provides file URIs for external drag-and-drop.

    When items are dragged out of this tree (e.g. to VS Code, a file
    manager, or another editor), the drop payload contains text/uri-list
    MIME data so the target application can open the file.
    """

    def __init__(self, ws_path_getter, parent=None):
        super().__init__(parent)
        self._ws_path_getter = ws_path_getter

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        mime = QMimeData()
        urls: list[QUrl] = []
        ws_path = self._ws_path_getter()
        for item in items:
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path and ws_path:
                full = Path(ws_path) / rel_path
                if full.exists():
                    urls.append(QUrl.fromLocalFile(str(full)))
        if urls:
            mime.setUrls(urls)
        return mime


class WorkspaceTab(QWidget):
    """Tab that lists workspaces and shows their directory trees."""

    commandRequested = Signal(dict, object)  # (command_spec, None)

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
        self._view_mode: str = "files"  # "files" or "objects"
        self._solve_cache: dict[str, object] = {}  # ws_path → SolveResult
        self._solver_thread: QThread | None = None
        self._solver_worker: QObject | None = None
        # Override support: candidate resolver + user-pending choices
        self._solve_resolver = None  # Resolver used for the last solve
        self._ws_overrides: dict[str, tuple[str, str]] = {}  # persisted: name → (version, artifact)
        self._pending_overrides: dict[str, tuple[str | None, str]] = {}  # name → (version|None=clear, artifact)
        self._override_thread: QThread | None = None
        self._override_worker: QObject | None = None

        self._setup_ui()
        self.destroyed.connect(self._cleanup_threads)

        if demo:
            self._load_demo()
        else:
            self._scan_workspaces()

    def _cleanup_threads(self):
        """Stop background threads before destruction."""
        for thread in (self._solver_thread,):
            if thread is not None and thread.isRunning():
                thread.quit()
                if not thread.wait(5000):
                    thread.terminate()
                    thread.wait()

    def _get_current_ws_path(self) -> str:
        """Return the current workspace directory path (for drag-and-drop)."""
        return self._ws_path

    def _create_command_buttons(self, parent_layout: QVBoxLayout) -> None:
        """Add draggable/sortable workspace command list to the left pane."""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #333333; max-height: 1px; margin: 6px 0;")
        parent_layout.addWidget(separator)

        lbl = QLabel("Commands")
        lbl.setStyleSheet(
            "color: #888888; font-size: 8pt; font-weight: bold; "
            "padding: 2px 4px;"
        )
        parent_layout.addWidget(lbl)

        self._cmd_list = QListWidget()
        self._cmd_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._cmd_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._cmd_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                border: 1px solid #333333;
                font-size: 8pt;
            }
            QListWidget::item {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #3A3A3A;
                border-radius: 3px;
                padding: 3px 6px;
                margin: 1px 0;
            }
            QListWidget::item:hover {
                background-color: #3A3A3A;
                border-color: #555555;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: #EEEEEE;
            }
        """)
        self._cmd_list.itemClicked.connect(self._on_command_item_clicked)

        # Populate with workspace commands
        specs = get_commands_for_group("workspace")
        for spec in specs:
            if spec is not None:
                item = QListWidgetItem(spec["title"])
                item.setToolTip(spec.get("description", ""))
                item.setData(Qt.ItemDataRole.UserRole, spec)
                self._cmd_list.addItem(item)

        # Register / Unregister workspace shortcuts
        reg_item = QListWidgetItem("Register Workspace")
        reg_item.setToolTip("Register a workspace directory in the manifest")
        reg_item.setData(Qt.ItemDataRole.UserRole, "__register__")
        self._cmd_list.addItem(reg_item)

        unreg_item = QListWidgetItem("Unregister Workspace")
        unreg_item.setToolTip("Unregister the selected workspace from the manifest")
        unreg_item.setData(Qt.ItemDataRole.UserRole, "__unregister__")
        self._cmd_list.addItem(unreg_item)

        parent_layout.addWidget(self._cmd_list, stretch=1)

    def _on_command_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle click on a command list item."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data == "__register__":
            self._on_register_workspace()
        elif data == "__unregister__":
            self._on_unregister_workspace()
        elif isinstance(data, dict):
            self.commandRequested.emit(data, None)

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
        left_layout.addWidget(self._ws_list, stretch=0)

        # Placeholder label shown when list is empty
        self._empty_label = QLabel("No workspaces found.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666666; font-size: 9pt; padding: 20px;")
        left_layout.addWidget(self._empty_label)

        # Workspace command buttons
        self._create_command_buttons(left_layout)

        splitter.addWidget(left)

        # Middle pane: toggle bar + stacked view (files / objects) + legend
        middle = QWidget()
        middle.setStyleSheet("background-color: #1E1E1E;")
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(4, 4, 4, 4)

        # Toggle bar: [Files] [Objects]  + workspace path
        toggle_bar = QWidget()
        toggle_bar.setStyleSheet("background-color: #252526; border-radius: 3px;")
        toggle_row = QHBoxLayout(toggle_bar)
        toggle_row.setContentsMargins(4, 2, 4, 2)
        toggle_row.setSpacing(0)

        toggle_style = """
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 4px 12px;
                font-size: 9pt;
            }
            QPushButton:checked {
                color: #EEEEEE;
                border-bottom: 2px solid #0078D4;
            }
            QPushButton:hover:!checked {
                color: #CCCCCC;
            }
        """
        self._files_btn = QPushButton("Files")
        self._files_btn.setCheckable(True)
        self._files_btn.setChecked(True)
        self._files_btn.setStyleSheet(toggle_style)
        self._files_btn.clicked.connect(lambda: self._set_view_mode("files"))
        toggle_row.addWidget(self._files_btn)

        self._objects_btn = QPushButton("Objects")
        self._objects_btn.setCheckable(True)
        self._objects_btn.setStyleSheet(toggle_style)
        self._objects_btn.clicked.connect(lambda: self._set_view_mode("objects"))
        toggle_row.addWidget(self._objects_btn)

        toggle_row.addSpacing(12)
        self._root_label = QLabel("")
        self._root_label.setStyleSheet(
            "color: #9CDCFE; font-size: 9pt; font-family: 'Consolas', monospace;"
        )
        self._root_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        toggle_row.addWidget(self._root_label, stretch=1)
        middle_layout.addWidget(toggle_bar)

        # Stacked view: page 0 = file tree, page 1 = object tree
        self._view_stack = QStackedWidget()

        # Page 0: file tree
        self._tree = _DragTreeWidget(self._get_current_ws_path)
        self._tree.setHeaderLabels(["Name", "Source"])
        self._tree.setRootIsDecorated(True)
        self._tree.setColumnWidth(0, 300)
        self._tree.setColumnWidth(1, 400)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._tree.currentItemChanged.connect(self._on_tree_item_selected)
        self._tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self._tree.itemExpanded.connect(self._on_tree_item_expanded)
        self._view_stack.addWidget(self._tree)

        # Page 1: object dependency tree (+ override action bar)
        obj_page = QWidget()
        obj_layout = QVBoxLayout(obj_page)
        obj_layout.setContentsMargins(0, 0, 0, 0)
        obj_layout.setSpacing(2)

        self._override_bar = QWidget()
        self._override_bar.setStyleSheet("background-color: #2D2D30; border-radius: 3px;")
        ov_row = QHBoxLayout(self._override_bar)
        ov_row.setContentsMargins(8, 2, 8, 2)
        self._override_label = QLabel("")
        self._override_label.setStyleSheet("color: #DCDCAA; font-size: 9pt;")
        ov_row.addWidget(self._override_label, stretch=1)
        self._override_revert_btn = QPushButton("Revert")
        self._override_revert_btn.setStyleSheet(
            "QPushButton { color: #CCCCCC; background: #3C3C3C; border: none;"
            " padding: 3px 10px; font-size: 9pt; border-radius: 2px; }"
            "QPushButton:hover { background: #4A4A4A; }"
        )
        self._override_revert_btn.clicked.connect(self._revert_pending_overrides)
        ov_row.addWidget(self._override_revert_btn)
        self._override_apply_btn = QPushButton("Apply Overrides")
        self._override_apply_btn.setStyleSheet(
            "QPushButton { color: #FFFFFF; background: #0078D4; border: none;"
            " padding: 3px 10px; font-size: 9pt; border-radius: 2px; }"
            "QPushButton:hover { background: #1C86DC; }"
            "QPushButton:disabled { background: #3C3C3C; color: #777777; }"
        )
        self._override_apply_btn.clicked.connect(self._apply_pending_overrides)
        ov_row.addWidget(self._override_apply_btn)
        self._override_bar.setVisible(False)
        obj_layout.addWidget(self._override_bar)

        self._obj_tree = QTreeWidget()
        self._obj_tree.setHeaderLabels(["Name", "Version", "Type", "Status", "Path"])
        self._obj_tree.setRootIsDecorated(True)
        self._obj_tree.setAlternatingRowColors(True)
        self._obj_tree.setColumnWidth(0, 280)
        self._obj_tree.currentItemChanged.connect(self._on_object_item_selected)
        obj_layout.addWidget(self._obj_tree, stretch=1)
        self._view_stack.addWidget(obj_page)

        middle_layout.addWidget(self._view_stack, stretch=1)

        splitter.addWidget(middle)

        # Right pane: file info
        self._info_pane = QWidget()
        self._info_pane.setStyleSheet("background-color: #1E1E1E;")
        self._info_pane.setMinimumWidth(200)
        info_layout = QVBoxLayout(self._info_pane)
        info_layout.setContentsMargins(8, 8, 8, 8)

        self._info_title = QLabel("File Info")
        self._info_title.setStyleSheet("color: #CCCCCC; font-size: 11pt; font-weight: bold;")
        info_layout.addWidget(self._info_title)

        self._info_content = QLabel("Select a file to view details.")
        self._info_content.setStyleSheet("color: #AAAAAA; font-size: 9pt;")
        self._info_content.setWordWrap(True)
        self._info_content.setTextFormat(Qt.TextFormat.RichText)
        self._info_content.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._info_content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._info_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        info_layout.addWidget(self._info_content, stretch=1)

        splitter.addWidget(self._info_pane)

        splitter.setStretchFactor(0, 1)  # workspace list ~15%
        splitter.setStretchFactor(1, 4)  # tree ~60%
        splitter.setStretchFactor(2, 2)  # info ~25%

        layout.addWidget(splitter)

    # ── Scanning ────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Clear and rescan workspaces (call after creating/deleting a workspace)."""
        self._ws_list.clear()
        self._tree.clear()
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

    def _on_register_workspace(self) -> None:
        """Register a workspace directory via folder picker."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Workspace Directory", "",
        )
        if not path:
            return
        ws_path = Path(path)
        try:
            from o3de_cli.commands.workspace import (
                _find_workspace_meta, _register_workspace,
            )
            if _find_workspace_meta(ws_path) is None:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Not a Workspace",
                    f"No workspace metadata found in:\n{ws_path}",
                )
                return
            _register_workspace(ws_path)
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Register Error", str(exc))
            return
        self.refresh()

    def _on_unregister_workspace(self) -> None:
        """Unregister the currently selected workspace."""
        current = self._ws_list.currentItem()
        if current is None:
            return
        ws_path = Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            from o3de_cli.commands.workspace import _unregister_workspace
            _unregister_workspace(ws_path)
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Unregister Error", str(exc))
            return
        self.refresh()

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
        self._obj_tree.clear()
        self._info_content.setText(
            "Select a file to view details."
            if self._view_mode == "files"
            else "Select an object to view details."
        )

        if current is None:
            self._root_label.setText("")
            return

        ws_path = current.data(Qt.ItemDataRole.UserRole)
        self._ws_path = ws_path or ""

        # Show workspace root path in header
        self._root_label.setText(self._ws_path)

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

        # Always show the full directory tree; use file_links for coloring
        self._start_tree_load(ws_path)

        # If in objects mode, auto-run solver for this workspace
        if self._view_mode == "objects":
            self._run_solver_if_needed()

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

    # ── View toggle (Files / Objects) ───────────────────────────────

    def _set_view_mode(self, mode: str) -> None:
        """Switch between 'files' and 'objects' views."""
        self._view_mode = mode
        if mode == "files":
            self._files_btn.setChecked(True)
            self._objects_btn.setChecked(False)
            self._view_stack.setCurrentIndex(0)
            self._info_title.setText("File Info")
            self._info_content.setText("Select a file to view details.")
        else:
            self._files_btn.setChecked(False)
            self._objects_btn.setChecked(True)
            self._view_stack.setCurrentIndex(1)
            self._info_title.setText("Object Info")
            self._info_content.setText("Select an object to view details.")
            self._run_solver_if_needed()

    def _run_solver_if_needed(self) -> None:
        """Run the solver if we don't have cached results for the current workspace."""
        if not self._ws_path:
            return
        cached = self._solve_cache.get(self._ws_path)
        if cached is not None:
            self._populate_object_tree(cached)
            return
        self._run_solver()

    def _run_solver(self) -> None:
        """Resolve workspace dependencies in a background thread."""
        if not self._ws_path:
            return

        self._obj_tree.clear()
        placeholder = QTreeWidgetItem(["Solving dependencies…"])
        placeholder.setForeground(0, QColor("#888888"))
        font = QFont()
        font.setItalic(True)
        placeholder.setFont(0, font)
        self._obj_tree.addTopLevelItem(placeholder)

        # Create resolver first — needed for canonical name lookup
        try:
            from o3de_cli.core import get_manifest_path, Resolver
            from o3de_cli.core.solver import solve_for_workspace

            manifest_path = get_manifest_path()
            if not manifest_path.exists():
                self._obj_tree.clear()
                err = QTreeWidgetItem(["No manifest found — cannot resolve dependencies"])
                err.setForeground(0, QColor("#F14C4C"))
                self._obj_tree.addTopLevelItem(err)
                return

            resolver = Resolver(manifest_path)
            resolver.resolve()
        except Exception as exc:
            self._obj_tree.clear()
            err = QTreeWidgetItem([f"Resolver error: {exc}"])
            err.setForeground(0, QColor("#F14C4C"))
            self._obj_tree.addTopLevelItem(err)
            return

        # Derive root name from workspace metadata
        try:
            from o3de_cli.commands.workspace import _read_workspace_meta
            meta = _read_workspace_meta(Path(self._ws_path))
            if meta is None or not meta.root_object:
                self._obj_tree.clear()
                err = QTreeWidgetItem(["No root object defined in workspace metadata"])
                err.setForeground(0, QColor("#F14C4C"))
                self._obj_tree.addTopLevelItem(err)
                return
            # Find canonical root name using resolver
            root_name = self._root_name_from_meta(meta, resolver)
            if not root_name:
                self._obj_tree.clear()
                err = QTreeWidgetItem([f"Root object not found in sources: {meta.root_object}"])
                err.setForeground(0, QColor("#F14C4C"))
                self._obj_tree.addTopLevelItem(err)
                return
        except Exception as exc:
            self._obj_tree.clear()
            err = QTreeWidgetItem([f"Error reading workspace: {exc}"])
            err.setForeground(0, QColor("#F14C4C"))
            self._obj_tree.addTopLevelItem(err)
            return

        # Background worker
        class _SolveWorker(QObject):
            finished = Signal(object)
            error = Signal(str)

            def __init__(self, r_name, res, pins):
                super().__init__()
                self._root_name = r_name
                self._resolver = res
                self._pins = pins

            def run(self):
                try:
                    result = solve_for_workspace(
                        root_name=self._root_name,
                        resolver=self._resolver,
                        overrides=self._pins or None,
                    )
                    self.finished.emit(result)
                except Exception as exc:
                    self.error.emit(str(exc))

        if self._solver_thread is not None:
            if self._solver_thread.isRunning():
                # Solver already in progress — skip; result will refresh when done
                return
            self._solver_thread.quit()
            self._solver_thread.wait()

        # Keep resolver + persisted overrides for candidate dropdowns
        self._solve_resolver = resolver
        self._ws_overrides = {
            n: (o.version, o.artifact) for n, o in meta.overrides.items()
        }
        self._pending_overrides.clear()
        self._update_override_bar()
        pins = {n: v for n, (v, _a) in self._ws_overrides.items()}

        worker = _SolveWorker(root_name, resolver, pins)
        thread = QThread(self)  # parent prevents premature GC
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # Bound-method connections give Qt a receiver context so the slots
        # are queued to the main thread (widgets must be created there).
        worker.finished.connect(self._on_solve_finished)
        worker.error.connect(self._on_solve_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        self._solver_thread = thread
        self._solver_worker = worker
        thread.start()

    @staticmethod
    def _root_name_from_meta(meta, resolver=None) -> str | None:
        """Derive the canonical root name from workspace metadata.

        First tries to match root_object path against the resolver's known
        objects (which use canonical names like org.o3de.project.foo).
        Falls back to matching against workspace sources.
        """
        root_path = meta.root_object
        if not root_path:
            return None
        root_p = Path(root_path).resolve()

        # Prefer resolver's canonical names (any object type — workspaces
        # can be rooted at gems/templates too, not just projects/engines)
        if resolver is not None:
            for name, obj in resolver.objects.items():
                obj_path = getattr(obj, "path", None)
                if obj_path and Path(obj_path).resolve() == root_p:
                    return name

        # Fallback: workspace source keys (all buckets)
        for type_dict in [meta.sources.engines, meta.sources.projects,
                          meta.sources.gems, meta.sources.templates]:
            for name, path in type_dict.items():
                if path and Path(path).resolve() == root_p:
                    return name
        return None

    def _on_solve_finished(self, result) -> None:
        """Handle solver completion — populate the object tree."""
        self._solve_cache[self._ws_path] = result
        if self._view_mode == "objects":
            self._populate_object_tree(result)

    def _on_solve_error(self, message: str) -> None:
        """Handle solver failure."""
        self._obj_tree.clear()
        err = QTreeWidgetItem([f"Solve error: {message}"])
        err.setForeground(0, QColor("#F14C4C"))
        self._obj_tree.addTopLevelItem(err)

    def _populate_object_tree(self, result) -> None:
        """Fill the object tree from a SolveResult."""
        from o3de_cli.core.solver import CandidateStatus

        _STATUS_COLORS = {
            CandidateStatus.LOCAL: QColor("#4EC9B0"),
            CandidateStatus.REMOTE: QColor("#569CD6"),
            CandidateStatus.UNKNOWN: QColor("#F14C4C"),
        }

        self._obj_tree.clear()

        root_cand = result.candidates.get(result.root_name)
        if not root_cand:
            return

        def _make_item(cand):
            item = QTreeWidgetItem([
                cand.name, cand.version, cand.object_type.value,
                cand.status.value.upper(),
                str(cand.path) if cand.path else "",
            ])
            color = _STATUS_COLORS.get(cand.status, QColor("#EEEEEE"))
            for col in range(5):
                item.setForeground(col, color)
            bold = QFont()
            bold.setBold(True)
            item.setFont(3, bold)
            return item

        root_item = _make_item(root_cand)
        self._obj_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

        for name, cand in sorted(result.candidates.items()):
            if name == result.root_name:
                continue
            child = _make_item(cand)
            root_item.addChild(child)
            self._attach_candidate_combo(child, cand)

            for overlay in result.overlays.get(name, []):
                ov_item = QTreeWidgetItem([
                    f"↳ {overlay.name}", overlay.version, "overlay",
                    overlay.status.value.upper(),
                    str(overlay.path) if overlay.path else "",
                ])
                for col in range(5):
                    ov_item.setForeground(col, QColor("#DCDCAA"))
                child.addChild(ov_item)

            child.setExpanded(bool(result.overlays.get(name)))

        # Root overlays
        for overlay in result.overlays.get(result.root_name, []):
            ov_item = QTreeWidgetItem([
                f"↳ {overlay.name}", overlay.version, "overlay",
                overlay.status.value.upper(),
                str(overlay.path) if overlay.path else "",
            ])
            for col in range(5):
                ov_item.setForeground(col, QColor("#DCDCAA"))
            root_item.addChild(ov_item)

        # Contained objects
        if result.children:
            header = QTreeWidgetItem([
                f"Contained Objects ({len(result.children)})", "", "", "", "",
            ])
            header.setForeground(0, QColor("#888888"))
            dim_font = QFont()
            dim_font.setItalic(True)
            header.setFont(0, dim_font)
            self._obj_tree.addTopLevelItem(header)
            for name, cand in sorted(result.children.items()):
                child = _make_item(cand)
                for col in range(5):
                    child.setForeground(col, QColor("#888888"))
                header.addChild(child)
                self._attach_candidate_combo(child, cand)

        self._obj_tree.resizeColumnToContents(1)
        self._obj_tree.resizeColumnToContents(2)
        self._obj_tree.resizeColumnToContents(3)

    # ── Candidate override dropdowns ──────────────────────────────

    _COMBO_STYLE = """
        QComboBox {
            background-color: #2D2D30; color: #DDDDDD;
            border: 1px solid #3C3C3C; border-radius: 2px;
            padding: 0px 4px; font-size: 8pt; min-height: 18px; max-height: 18px;
        }
        QComboBox QAbstractItemView {
            background-color: #252526; color: #DDDDDD;
            selection-background-color: #0078D4;
        }
    """

    def _attach_candidate_combo(self, item: QTreeWidgetItem, cand) -> None:
        """Embed a version/artifact dropdown in the Version column when the
        object has more than one selectable candidate (or an override)."""
        if self._solve_resolver is None:
            return
        try:
            from o3de_cli.core.solver import list_candidates, CandidateStatus
            candidates = list_candidates(cand.name, self._solve_resolver)
        except Exception:
            return

        persisted = self._ws_overrides.get(cand.name)

        # Build entries: (label, data, enabled); data None = auto/clear
        entries: list[tuple[str, tuple | None, bool]] = []
        if persisted:
            entries.append(("auto (solver default)", None, True))
        for c in candidates:
            if c.status == CandidateStatus.LOCAL and c.path:
                entries.append((f"{c.version} — source", (c.version, "source"), True))
            elif c.status == CandidateStatus.REMOTE:
                entries.append(
                    (f"{c.version} — remote (not installed)", (c.version, "source"), False)
                )
            if c.local_binary_path:
                entries.append(
                    (f"{c.version} — local build", (c.version, "local-binary"), True)
                )
            if c.remote_binary:
                entries.append(
                    (f"{c.version} — binary (remote)", (c.version, "remote-binary"), True)
                )

        selectable = sum(1 for _l, _d, en in entries if en)
        if selectable <= 1 and not persisted:
            return  # nothing to choose — keep the plain text cell

        combo = QComboBox()
        combo.setStyleSheet(self._COMBO_STYLE)
        for label, data, enabled in entries:
            combo.addItem(label, userData=data)
            if not enabled:
                model_item = combo.model().item(combo.count() - 1)
                if model_item is not None:
                    model_item.setEnabled(False)

        # Current selection: persisted override, else the chosen candidate
        want = persisted if persisted else (cand.version, "source")
        for idx in range(combo.count()):
            if combo.itemData(idx) == tuple(want):
                combo.setCurrentIndex(idx)
                break

        combo.currentIndexChanged.connect(
            lambda _idx, name=cand.name, cb=combo: self._on_override_combo_changed(name, cb)
        )
        self._obj_tree.setItemWidget(item, 1, combo)

    def _on_override_combo_changed(self, name: str, combo: QComboBox) -> None:
        """Record a pending override when the user picks a different candidate."""
        data = combo.currentData()
        persisted = self._ws_overrides.get(name)

        if data is None:
            # "auto" — clear the persisted override
            if persisted:
                self._pending_overrides[name] = (None, "source")
            else:
                self._pending_overrides.pop(name, None)
        else:
            version, artifact = data
            if persisted and tuple(persisted) == (version, artifact):
                self._pending_overrides.pop(name, None)
            elif not persisted and artifact == "source" and self._is_solver_choice(name, version):
                self._pending_overrides.pop(name, None)
            else:
                self._pending_overrides[name] = (version, artifact)
        self._update_override_bar()

    def _is_solver_choice(self, name: str, version: str) -> bool:
        """True if version matches what the solver currently chose for name."""
        result = self._solve_cache.get(self._ws_path)
        if result is None:
            return False
        cand = result.candidates.get(name) or result.children.get(name)
        return bool(cand and cand.version == version)

    def _update_override_bar(self) -> None:
        """Show/hide the pending-overrides action bar."""
        count = len(self._pending_overrides)
        if count:
            names = ", ".join(sorted(self._pending_overrides)[:3])
            more = f" (+{count - 3} more)" if count > 3 else ""
            self._override_label.setText(
                f"{count} pending override{'s' if count != 1 else ''}: {names}{more}"
            )
        self._override_bar.setVisible(bool(count))

    def _revert_pending_overrides(self) -> None:
        """Discard pending choices and restore combos to persisted state."""
        self._pending_overrides.clear()
        self._update_override_bar()
        cached = self._solve_cache.get(self._ws_path)
        if cached is not None:
            self._populate_object_tree(cached)

    def _apply_pending_overrides(self) -> None:
        """Persist pending overrides via `o3de workspace override` and refresh."""
        if not self._pending_overrides or not self._ws_path:
            return

        import sys as _sys

        ws_path = self._ws_path
        pending = dict(self._pending_overrides)
        self._override_apply_btn.setEnabled(False)
        self._override_label.setText("Applying overrides…")

        class _OverrideWorker(QObject):
            finished = Signal(list)  # list of error strings (empty = success)

            def run(self):
                import subprocess
                errors: list[str] = []
                for obj_name, (version, artifact) in pending.items():
                    args = [
                        _sys.executable, "-m", "o3de_cli",
                        "workspace", "override", ws_path, obj_name,
                    ]
                    if version is None:
                        args.append("--clear")
                    else:
                        args += ["--version", version, "--artifact", artifact]
                    try:
                        proc = subprocess.run(
                            args, capture_output=True, text=True, timeout=600,
                        )
                        if proc.returncode != 0:
                            detail = (proc.stderr or proc.stdout or "").strip()
                            errors.append(f"{obj_name}: {detail[-400:]}")
                    except Exception as exc:
                        errors.append(f"{obj_name}: {exc}")
                self.finished.emit(errors)

        if self._override_thread is not None and self._override_thread.isRunning():
            return

        worker = _OverrideWorker()
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_overrides_applied)
        worker.finished.connect(thread.quit)
        self._override_thread = thread
        self._override_worker = worker
        thread.start()

    def _on_overrides_applied(self, errors: list) -> None:
        """Refresh views after overrides were applied (or report failures)."""
        self._override_apply_btn.setEnabled(True)
        self._pending_overrides.clear()
        self._update_override_bar()

        if errors:
            QMessageBox.warning(
                self, "Override errors",
                "Some overrides could not be applied:\n\n" + "\n".join(errors),
            )

        # Invalidate caches and reload — links + solve state changed on disk
        if self._ws_path:
            self._solve_cache.pop(self._ws_path, None)
            self._file_links = self._load_file_links(self._ws_path)
            unique_owners = sorted(set(self._source_paths.keys()))
            self._colors = _assign_colors(unique_owners)
            self._start_tree_load(self._ws_path)
            self._run_solver()

    def _on_object_item_selected(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        """Show object details in the right info pane."""
        if current is None:
            self._info_content.setText("Select an object to view details.")
            return
        name = current.text(0)
        version = current.text(1)
        obj_type = current.text(2)
        status = current.text(3)
        path = current.text(4)

        if not version and not obj_type:
            self._info_content.setText("")
            return

        lines = [f"<b>Name:</b> {name}"]
        if version:
            lines.append(f"<b>Version:</b> {version}")
        if obj_type:
            lines.append(f"<b>Type:</b> {obj_type}")
        if status:
            color_map = {"LOCAL": "#4EC9B0", "REMOTE": "#569CD6", "UNKNOWN": "#F14C4C"}
            scolor = color_map.get(status, "#EEEEEE")
            lines.append(f"<b>Status:</b> <span style='color:{scolor}'>{status}</span>")
        if path:
            lines.append(f"<b>Path:</b> {path}")
        self._info_content.setText("<br>".join(lines))

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

        style = self.style()
        folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

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
                item.setData(0, Qt.ItemDataRole.UserRole, partial)
                is_leaf = i == len(parts) - 1
                item.setData(0, Qt.ItemDataRole.UserRole + 1, not is_leaf)
                if is_leaf:
                    item.setIcon(0, file_icon)
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
                    source_abs = dest_to_source[dest_rel]
                    owner = self._owner_for_source(source_abs)
                    color = self._colors.get(owner)
                    if color:
                        item.setForeground(0, QBrush(color))
                        item.setForeground(1, QBrush(QColor("#555555")))
                    item.setText(1, source_abs)
                    item.setToolTip(1, source_abs)
                else:
                    item.setIcon(0, folder_icon)
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, True)
                parent_path = "/".join(parts[:i]) if i > 0 else ""
                if parent_path and parent_path in nodes:
                    nodes[parent_path].addChild(item)
                else:
                    self._tree.addTopLevelItem(item)
                nodes[partial] = item

        self._tree.expandToDepth(0)

    _PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 2  # marks dummy child for lazy load

    def _start_tree_load(self, ws_path: str) -> None:
        """Load top-level directory entries (lazy — subfolders load on expand)."""
        self._tree.clear()
        self._load_children_for(ws_path, "", None)

    def _load_children_for(self, ws_path: str, parent_rel: str, parent_item: QTreeWidgetItem | None) -> None:
        """Load immediate children of a directory into the tree."""
        root = Path(ws_path)
        target = root / parent_rel if parent_rel else root
        if not target.is_dir():
            return

        style = self.style()
        folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        # Reverse lookup for file_links
        dest_to_source: dict[str, str] = (
            {v: k for k, v in self._file_links.items()} if self._file_links else {}
        )

        try:
            children = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        except (PermissionError, OSError):
            return

        has_children = False
        for child in children:
            if child.name.startswith("."):
                continue
            has_children = True
            is_dir = child.is_dir()
            rel_path = child.relative_to(root).as_posix()

            item = QTreeWidgetItem()
            item.setText(0, child.name)
            item.setData(0, Qt.ItemDataRole.UserRole, rel_path)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, is_dir)

            if is_dir:
                item.setIcon(0, folder_icon)
                # Add placeholder so expand arrow appears
                dummy = QTreeWidgetItem()
                dummy.setData(0, self._PLACEHOLDER_ROLE, True)
                item.addChild(dummy)
            else:
                item.setIcon(0, file_icon)
                source = dest_to_source.get(rel_path, "")
                if not source:
                    try:
                        if child.is_symlink():
                            source = str(child.resolve())
                    except (OSError, ValueError):
                        pass
                if source:
                    owner = self._owner_for_source(source)
                    color = self._colors.get(owner)
                    if color:
                        item.setForeground(0, QBrush(color))
                        item.setForeground(1, QBrush(QColor("#555555")))
                    item.setText(1, source)
                    item.setToolTip(0, source)

            if parent_item is not None:
                parent_item.addChild(item)
            else:
                self._tree.addTopLevelItem(item)

        if not has_children and parent_item is None:
            placeholder = QTreeWidgetItem()
            placeholder.setText(0, "(empty workspace -- no files found)")
            placeholder.setForeground(0, QBrush(QColor("#666666")))
            self._tree.addTopLevelItem(placeholder)

    def _on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Lazily load children when a folder is expanded for the first time."""
        if item.childCount() == 1 and item.child(0).data(0, self._PLACEHOLDER_ROLE):
            item.removeChild(item.child(0))
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            ws_path = self._ws_path
            if ws_path and rel_path is not None:
                self._load_children_for(ws_path, rel_path, item)

    def _on_tree_context_menu(self, pos) -> None:
        """Show right-click menu with copy options."""
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
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)

        if name:
            act = menu.addAction("Copy Name")
            act.triggered.connect(lambda _=False, t=name: QApplication.clipboard().setText(t))
        if source:
            act = menu.addAction("Copy Source Path")
            act.triggered.connect(lambda _=False, t=source: QApplication.clipboard().setText(t))
        if rel_path and self._ws_path:
            dest_full = str(Path(self._ws_path) / rel_path)
            act = menu.addAction("Copy Destination Path")
            act.triggered.connect(lambda _=False, t=dest_full: QApplication.clipboard().setText(t))
            act = menu.addAction("Open in File Explorer")
            act.triggered.connect(lambda _=False, p=dest_full: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(p).parent))
            ))

        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_tree_item_selected(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        """Show file info in the right pane when a tree item is selected."""
        if current is None:
            self._info_content.setText("Select a file to view details.")
            return

        rel_path = current.data(0, Qt.ItemDataRole.UserRole)
        is_dir = current.data(0, Qt.ItemDataRole.UserRole + 1)

        if not rel_path:
            self._info_content.setText("")
            return

        name = current.text(0)
        source = current.text(1)
        dest_full = str(Path(self._ws_path) / rel_path) if self._ws_path else rel_path

        lines = [f"<b>Name:</b> {name}"]
        lines.append(f"<b>Type:</b> {'Folder' if is_dir else 'File'}")
        lines.append(f"<b>Relative Path:</b> {rel_path}")
        lines.append(f"<b>Destination:</b> {dest_full}")
        if source:
            lines.append(f"<b>Source:</b> {source}")
            owner = self._owner_for_source(source)
            if owner:
                lines.append(f"<b>Owner:</b> {owner}")

        # File stats
        try:
            p = Path(dest_full)
            if p.exists() and not is_dir:
                stat = p.stat()
                size = stat.st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                lines.append(f"<b>Size:</b> {size_str}")
                from datetime import datetime
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"<b>Modified:</b> {mtime}")
                if p.is_symlink():
                    lines.append(f"<b>Link Target:</b> {p.resolve()}")
        except (OSError, ValueError):
            pass

        self._info_content.setText("<br>".join(lines))

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Double-click opens the destination file with the default OS program."""
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not rel_path or not self._ws_path:
            return
        dest_full = Path(self._ws_path) / rel_path
        if is_dir:
            # Open folder in explorer
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest_full)))
        else:
            # Open file with default associated program
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest_full)))
