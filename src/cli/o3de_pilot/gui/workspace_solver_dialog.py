# O3DE Pilot GUI - Workspace Solver Dialog
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Modal dialog that runs the workspace solver against a chosen root object
and displays the resolved dependency graph with local/remote/unknown
status coloring.  Users can download remote items or reorder overlays
before creating a workspace.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import ObjectType, Resolver, Store, get_manifest_path
from ..core.solver import (
    CandidateStatus,
    Candidate,
    OverlayEntry,
    SolveResult,
    solve_for_workspace,
)

logger = logging.getLogger("o3de_pilot.gui.solver")


# ── Status colours ──────────────────────────────────────────────────────────

_STATUS_COLORS: dict[CandidateStatus, QColor] = {
    CandidateStatus.LOCAL: QColor("#4EC9B0"),   # green
    CandidateStatus.REMOTE: QColor("#569CD6"),  # blue
    CandidateStatus.UNKNOWN: QColor("#F14C4C"), # red
}

_OVERLAY_COLOR = QColor("#DCDCAA")  # yellow-ish for overlays


# ── Dark-theme stylesheet ──────────────────────────────────────────────────

_SOLVER_STYLE = """
QDialog {
    background-color: #1E1E1E;
    color: #EEEEEE;
}
QLabel {
    color: #EEEEEE;
    font-size: 9pt;
}
QLabel#section_header {
    color: #CCCCCC;
    font-size: 10pt;
    font-weight: bold;
    padding-top: 4px;
}
QComboBox {
    background-color: #2D2D2D;
    color: #EEEEEE;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 9pt;
    selection-background-color: #0078D4;
    min-width: 250px;
}
QComboBox:focus {
    border-color: #0078D4;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #CCCCCC;
}
QTreeWidget {
    background-color: #1E1E1E;
    color: #EEEEEE;
    border: 1px solid #444444;
    border-radius: 4px;
    font-size: 9pt;
    alternate-background-color: #252525;
    selection-background-color: #094771;
}
QTreeWidget::item {
    padding: 4px 0;
}
QHeaderView::section {
    background-color: #2D2D2D;
    color: #CCCCCC;
    border: none;
    border-right: 1px solid #444444;
    padding: 6px 8px;
    font-size: 8pt;
    font-weight: bold;
}
QGroupBox {
    color: #CCCCCC;
    border: 1px solid #444444;
    border-radius: 4px;
    margin-top: 12px;
    padding: 12px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background-color: #333333;
    color: #EEEEEE;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 9pt;
    min-width: 70px;
}
QPushButton:hover {
    border-color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #555555;
}
QPushButton:disabled {
    color: #666666;
    border-color: #444444;
}
QPushButton#primary {
    background-color: #0078D4;
    border-color: #0078D4;
}
QPushButton#primary:hover {
    background-color: #1A8AE8;
}
QPlainTextEdit {
    background-color: #1E1E1E;
    color: #AAAAAA;
    border: 1px solid #444444;
    border-radius: 4px;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 8pt;
}
QDialogButtonBox QPushButton {
    min-width: 90px;
}
"""


# ── Background worker ──────────────────────────────────────────────────────

class _SolveWorker(QObject):
    """Runs the solver in a background thread."""

    progress = Signal(str)          # status message
    finished = Signal(object)       # SolveResult
    error = Signal(str)             # error message

    def __init__(
        self,
        root_name: str,
        resolver: Resolver,
        store: Optional[Store],
    ):
        super().__init__()
        self._root_name = root_name
        self._resolver = resolver
        self._store = store

    def run(self) -> None:
        try:
            result = solve_for_workspace(
                root_name=self._root_name,
                resolver=self._resolver,
                store=self._store,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Dialog ─────────────────────────────────────────────────────────────────

class WorkspaceSolverDialog(QDialog):
    """Modal dialog that resolves a workspace dependency graph.

    Usage::

        dlg = WorkspaceSolverDialog(resolver=resolver, store=store, parent=mw)
        if dlg.exec() == QDialog.Accepted:
            result = dlg.result()
    """

    def __init__(
        self,
        *,
        resolver: Resolver,
        store: Optional[Store] = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._resolver = resolver
        self._store = store
        self._solve_result: Optional[SolveResult] = None
        self._thread: Optional[QThread] = None

        self._setup_ui()
        self.setStyleSheet(_SOLVER_STYLE)

    # ── public API ──────────────────────────────────────────────────

    def solve_result(self) -> Optional[SolveResult]:
        """Return the last successful solve result, or *None*."""
        return self._solve_result

    # ── UI construction ─────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Workspace Solver")
        self.setMinimumSize(800, 600)
        self.resize(950, 700)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 12)

        # ── Top row: root selector + solve button ───────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        lbl = QLabel("Root object:")
        top_row.addWidget(lbl)

        self._root_combo = QComboBox()
        self._root_combo.setEditable(False)
        self._populate_root_combo()
        top_row.addWidget(self._root_combo, 1)

        self._include_store_checkbox = None
        if self._store is not None:
            from PySide6.QtWidgets import QCheckBox
            self._include_store_checkbox = QCheckBox("Include store")
            self._include_store_checkbox.setChecked(True)
            self._include_store_checkbox.setStyleSheet(
                "QCheckBox { color: #EEEEEE; font-size: 9pt; }"
            )
            top_row.addWidget(self._include_store_checkbox)

        self._solve_btn = QPushButton("Solve")
        self._solve_btn.setObjectName("primary")
        self._solve_btn.clicked.connect(self._on_solve)
        top_row.addWidget(self._solve_btn)

        root.addLayout(top_row)

        # ── Splitter: results tree  |  log pane ─────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Results tree
        self._tree = QTreeWidget()
        self._tree.setAlternatingRowColors(True)
        self._tree.setHeaderLabels(["Name", "Version", "Type", "Status", "Path"])
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setColumnWidth(0, 280)
        splitter.addWidget(self._tree)

        # Log pane
        log_group = QGroupBox("Solver Log")
        log_layout = QVBoxLayout(log_group)
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(150)
        log_layout.addWidget(self._log_text)
        splitter.addWidget(log_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # ── Summary bar ─────────────────────────────────────────────
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            "QLabel { color: #AAAAAA; font-size: 8pt; padding-top: 4px; }"
        )
        root.addWidget(self._summary_label)

        # ── Button box ──────────────────────────────────────────────
        btn_box = QDialogButtonBox()

        self._download_btn = QPushButton("Download Remote")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download_remote)
        btn_box.addButton(self._download_btn, QDialogButtonBox.ButtonRole.ActionRole)

        self._accept_btn = btn_box.addButton(QDialogButtonBox.StandardButton.Ok)
        self._accept_btn.setText("Accept")
        self._accept_btn.setEnabled(False)
        self._accept_btn.clicked.connect(self.accept)

        cancel_btn = btn_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.clicked.connect(self.reject)

        root.addWidget(btn_box)

    # ── Root combo population ───────────────────────────────────────

    def _populate_root_combo(self) -> None:
        """Fill the combo with engines and projects from the resolver."""
        roots: list[str] = []
        for name, obj in sorted(self._resolver.objects.items()):
            if obj.object_type in (ObjectType.ENGINE, ObjectType.PROJECT):
                label = f"{obj.object_type.value}: {name} ({obj.version})"
                self._root_combo.addItem(label, userData=name)

    # ── Solve logic ─────────────────────────────────────────────────

    def _on_solve(self) -> None:
        """Run the solver in a background thread."""
        root_name = self._root_combo.currentData()
        if not root_name:
            return

        self._solve_btn.setEnabled(False)
        self._accept_btn.setEnabled(False)
        self._download_btn.setEnabled(False)
        self._tree.clear()
        self._log_text.clear()
        self._summary_label.setText("Solving…")
        QApplication.processEvents()

        include_store = (
            self._store
            if (self._include_store_checkbox and self._include_store_checkbox.isChecked())
            else None
        )

        worker = _SolveWorker(root_name, self._resolver, include_store)
        thread = QThread()
        worker.moveToThread(thread)

        worker.progress.connect(self._on_progress)
        worker.finished.connect(lambda r: self._on_finished(r))
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.started.connect(worker.run)

        # prevent GC
        self._thread = thread
        self._worker = worker

        thread.start()

    def _on_progress(self, message: str) -> None:
        self._log_text.appendPlainText(message)

    def _on_finished(self, result: SolveResult) -> None:
        self._solve_result = result
        self._solve_btn.setEnabled(True)
        self._populate_tree(result)
        self._update_summary(result)

        if result.is_resolved:
            self._accept_btn.setEnabled(True)
            if result.remote_count > 0:
                self._download_btn.setEnabled(True)
        else:
            self._log_text.appendPlainText(
                f"\n⚠ Conflict: {result.conflict_message}"
            )

    def _on_error(self, message: str) -> None:
        self._solve_btn.setEnabled(True)
        self._log_text.appendPlainText(f"\n✖ Error: {message}")
        self._summary_label.setText("Solver error")

    # ── Tree population ─────────────────────────────────────────────

    def _populate_tree(self, result: SolveResult) -> None:
        self._tree.clear()

        # Root node
        root_cand = result.candidates.get(result.root_name)
        if root_cand:
            root_item = self._make_item(root_cand)
            self._tree.addTopLevelItem(root_item)
            root_item.setExpanded(True)

            # Dependencies resolved by the solver
            dep_items = []
            for name, cand in sorted(result.candidates.items()):
                if name == result.root_name:
                    continue
                child_item = self._make_item(cand)
                root_item.addChild(child_item)
                dep_items.append(child_item)

                # Overlays for this candidate
                for overlay in result.overlays.get(name, []):
                    overlay_item = self._make_overlay_item(overlay)
                    child_item.addChild(overlay_item)

                child_item.setExpanded(bool(result.overlays.get(name)))

            # Root-level overlays
            for overlay in result.overlays.get(result.root_name, []):
                overlay_item = self._make_overlay_item(overlay)
                root_item.addChild(overlay_item)

        # Containment children (not dependencies) — shown in a separate section
        if result.children:
            children_header = QTreeWidgetItem([
                f"Contained Objects ({len(result.children)})",
                "", "", "", "",
            ])
            children_header.setForeground(0, QColor("#888888"))
            dim_font = QFont()
            dim_font.setItalic(True)
            children_header.setFont(0, dim_font)
            self._tree.addTopLevelItem(children_header)
            children_header.setExpanded(False)

            for name, cand in sorted(result.children.items()):
                child_item = self._make_item(cand)
                # Dim containment children to distinguish from deps
                for col in range(5):
                    child_item.setForeground(col, QColor("#888888"))
                children_header.addChild(child_item)

        self._tree.resizeColumnToContents(1)
        self._tree.resizeColumnToContents(2)
        self._tree.resizeColumnToContents(3)

    def _make_item(self, cand: Candidate) -> QTreeWidgetItem:
        """Create a tree item for a resolved candidate."""
        status_text = cand.status.value.upper()
        path_text = str(cand.path) if cand.path else ""
        item = QTreeWidgetItem([
            cand.name,
            cand.version,
            cand.object_type.value,
            status_text,
            path_text,
        ])

        color = _STATUS_COLORS.get(cand.status, QColor("#EEEEEE"))
        for col in range(5):
            item.setForeground(col, color)

        # Bold the status column
        status_font = QFont()
        status_font.setBold(True)
        item.setFont(3, status_font)

        return item

    def _make_overlay_item(self, overlay: OverlayEntry) -> QTreeWidgetItem:
        """Create a tree item for an overlay."""
        item = QTreeWidgetItem([
            f"↳ {overlay.name}",
            overlay.version,
            "overlay",
            overlay.status.value.upper(),
            str(overlay.path) if overlay.path else "",
        ])

        for col in range(5):
            item.setForeground(col, _OVERLAY_COLOR)

        return item

    # ── Summary ─────────────────────────────────────────────────────

    def _update_summary(self, result: SolveResult) -> None:
        parts = []
        dep_count = len(result.candidates) - 1  # exclude root
        parts.append(f"{dep_count} dependenc{'y' if dep_count == 1 else 'ies'}")
        parts.append(f"{result.local_count} local")
        if result.remote_count:
            parts.append(f"{result.remote_count} remote")
        if result.unknown_count:
            parts.append(f"{result.unknown_count} unknown")
        if result.children:
            parts.append(f"{len(result.children)} contained")
        overlay_count = sum(len(v) for v in result.overlays.values())
        if overlay_count:
            parts.append(f"{overlay_count} overlay{'s' if overlay_count != 1 else ''}")

        status = "✔ Resolved" if result.is_resolved else "✖ Conflict"
        self._summary_label.setText(f"{status}  —  {' · '.join(parts)}")

    # ── Download remote items ───────────────────────────────────────

    def _on_download_remote(self) -> None:
        """Placeholder for downloading remote candidates."""
        if not self._solve_result:
            return

        remote_names = [
            c.name for c in self._solve_result.candidates.values()
            if c.status == CandidateStatus.REMOTE
        ]

        if not remote_names:
            return

        QMessageBox.information(
            self,
            "Download Remote Objects",
            f"The following {len(remote_names)} object(s) need to be "
            f"downloaded from the store before building the workspace:\n\n"
            + "\n".join(f"  • {n}" for n in remote_names)
            + "\n\nDownload support coming soon.",
        )
