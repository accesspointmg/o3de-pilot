# O3DE Pilot GUI - Command Parameter Dialog
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Reusable modal dialog that renders parameter fields for a CLI command spec
and returns a dict of user-supplied values.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── Dark-theme stylesheet ──────────────────────────────────────────────────

_DIALOG_STYLE = """
QDialog {
    background-color: #1E1E1E;
    color: #EEEEEE;
}
QLabel {
    color: #EEEEEE;
    font-size: 9pt;
}
QLabel#description {
    color: #AAAAAA;
    font-size: 8pt;
    padding-bottom: 8px;
}
QLabel#required_star {
    color: #FF6666;
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
QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #2D2D2D;
    color: #EEEEEE;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 9pt;
    selection-background-color: #0078D4;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: #0078D4;
}
QCheckBox {
    color: #EEEEEE;
    spacing: 6px;
    font-size: 9pt;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #2D2D2D;
}
QCheckBox::indicator:checked {
    background-color: #0078D4;
    border-color: #0078D4;
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
QPushButton#primary {
    background-color: #0078D4;
    border-color: #0078D4;
}
QPushButton#primary:hover {
    background-color: #1A8AE8;
}
QPushButton#browse {
    min-width: 32px;
    padding: 4px 10px;
    font-size: 8pt;
}
QComboBox QAbstractItemView {
    background-color: #2D2D2D;
    color: #EEEEEE;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
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
QPlainTextEdit {
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 8pt;
}
"""


# ── CommandDialog ──────────────────────────────────────────────────────────

class CommandDialog(QDialog):
    """Modal dialog to collect parameters for a CLI command.

    Usage::

        spec = COMMAND_SPECS["gem create"]
        dlg = CommandDialog(spec, parent=main_window,
                            selected_object=current_obj)
        if dlg.exec() == QDialog.Accepted:
            args = dlg.get_values()      # dict[str, str|bool]
            tokens = dlg.build_tokens()  # ["gem", "create", "--name", ...]
    """

    def __init__(self, spec: dict, *, parent: QWidget | None = None,
                 selected_object: Any = None):
        super().__init__(parent)
        self._spec = spec
        self._selected_object = selected_object
        self._field_widgets: dict[str, QWidget] = {}
        self._setup_ui()
        self.setStyleSheet(_DIALOG_STYLE)

    # ── UI construction ────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle(self._spec["title"])
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        # Description
        desc_label = QLabel(self._spec.get("description", ""))
        desc_label.setObjectName("description")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # CLI command preview
        cli_preview_text = " ".join(self._spec["cli_args"])
        cli_label = QLabel(f"o3de-pilot {cli_preview_text}")
        cli_label.setStyleSheet(
            "color: #888888; font-family: 'Cascadia Code', 'Consolas', monospace; "
            "font-size: 8pt; padding: 4px 0;"
        )
        layout.addWidget(cli_label)

        # Fields group
        if self._spec.get("fields"):
            group = QGroupBox("Parameters")
            form = QFormLayout(group)
            form.setSpacing(10)
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

            for field in self._spec["fields"]:
                widget = self._create_field_widget(field)
                self._field_widgets[field["name"]] = widget

                # Label with red asterisk for required
                label_text = field["label"]
                if field.get("required"):
                    label_text += " *"
                label = QLabel(label_text)
                if field.get("required"):
                    label.setStyleSheet("color: #EEEEEE; font-size: 9pt;")

                if field["type"] == "flag":
                    # Checkbox is self-labelling — put it in the value column
                    form.addRow("", widget)
                elif field["type"] == "path":
                    # Path: line edit + browse button in a row
                    row = QHBoxLayout()
                    row.setSpacing(4)
                    row.addWidget(widget, 1)
                    browse = QPushButton("…")
                    browse.setObjectName("browse")
                    browse.setToolTip("Browse…")
                    browse.clicked.connect(
                        lambda _, w=widget: self._browse_path(w)
                    )
                    row.addWidget(browse)
                    form.addRow(label, row)
                elif field["type"] == "file":
                    # File: line edit + browse button for file selection
                    row = QHBoxLayout()
                    row.setSpacing(4)
                    row.addWidget(widget, 1)
                    browse = QPushButton("\u2026")
                    browse.setObjectName("browse")
                    browse.setToolTip("Browse\u2026")
                    file_filter = field.get("file_filter", "All Files (*)")
                    browse.clicked.connect(
                        lambda _, w=widget, ff=file_filter: self._browse_file(w, ff)
                    )
                    row.addWidget(browse)
                    form.addRow(label, row)
                else:
                    form.addRow(label, widget)

            layout.addWidget(group)

        # Spacer
        layout.addStretch(1)

        # Button box
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        ok_btn = btn_box.button(QDialogButtonBox.Ok)
        ok_btn.setText("Run")
        ok_btn.setObjectName("primary")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ── Field widget factory ───────────────────────────────────────

    def _create_field_widget(self, field: dict) -> QWidget:
        ftype = field["type"]
        default = field.get("default", "")

        # Pre-fill from selected object if applicable
        prefill = ""
        from_sel = field.get("from_selected", "")
        if from_sel and self._selected_object is not None:
            prefill = getattr(self._selected_object, from_sel, "") or ""
            if prefill:
                prefill = str(prefill)

        if ftype == "flag":
            cb = QCheckBox(field["label"])
            if default:
                cb.setChecked(True)
            return cb

        if ftype == "choice":
            combo = QComboBox()
            choices = field.get("choices", [])
            combo.addItems(choices)
            if default and default in choices:
                combo.setCurrentText(default)
            elif prefill and prefill in choices:
                combo.setCurrentText(prefill)
            return combo

        if ftype == "root_object":
            # Radio buttons (Project / Engine) + combo of known objects
            from PySide6.QtWidgets import QRadioButton, QButtonGroup
            container = QWidget()
            container.setObjectName("root_object_container")
            vlayout = QVBoxLayout(container)
            vlayout.setContentsMargins(0, 0, 0, 0)
            vlayout.setSpacing(6)

            radio_row = QWidget()
            radio_layout = QHBoxLayout(radio_row)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            rb_project = QRadioButton("Project")
            rb_engine = QRadioButton("Engine")
            rb_project.setStyleSheet("color: #EEEEEE;")
            rb_engine.setStyleSheet("color: #EEEEEE;")
            rb_project.setChecked(True)
            btn_group = QButtonGroup(container)
            btn_group.addButton(rb_project, 0)
            btn_group.addButton(rb_engine, 1)
            radio_layout.addWidget(rb_project)
            radio_layout.addWidget(rb_engine)
            radio_layout.addStretch()
            vlayout.addWidget(radio_row)

            combo = QComboBox()
            combo.setObjectName("root_object_combo")
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            vlayout.addWidget(combo)

            # Populate helper
            def _populate_root_combo(type_name: str):
                combo.clear()
                try:
                    from o3de_cli.core.resolver import Resolver
                    resolver = Resolver()
                    resolver.resolve()
                    for obj_name, obj in sorted(resolver.objects.items()):
                        if obj.object_type and obj.object_type.value == type_name:
                            combo.addItem(obj_name)
                except Exception:
                    combo.addItem("(none available)")

            _populate_root_combo("project")

            def _on_radio_toggled(btn_id):
                _populate_root_combo("project" if btn_id == 0 else "engine")

            btn_group.idClicked.connect(_on_radio_toggled)
            return container

        if ftype == "template_choice":
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            combo = QComboBox()
            combo.setEditable(True)
            combo.setObjectName("template_combo")
            # Populate from known templates and select the default
            default_index = 0
            try:
                from o3de_cli.core.resolver import Resolver
                resolver = Resolver()
                resolver.resolve()
                # Filter templates by their type field matching the command's object type
                obj_types = self._spec.get("object_types", [])
                filter_type = obj_types[0] if obj_types else ""
                sorted_names = sorted(resolver.templates.keys())
                idx = 0
                for tpl_name in sorted_names:
                    tpl = resolver.templates[tpl_name]
                    tpl_type = tpl.data.get("template", {}).get("type", "")
                    if filter_type and filter_type != "template" and tpl_type != filter_type:
                        continue
                    combo.addItem(tpl_name)
                    if "default" in tpl_name.lower():
                        default_index = idx
                    idx += 1
            except Exception:
                combo.addItem("(none available)")
            if combo.count() > 0:
                combo.setCurrentIndex(default_index)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            browse_btn = QPushButton("...")
            browse_btn.setFixedWidth(32)
            browse_btn.setToolTip("Browse for a template directory")
            browse_btn.clicked.connect(
                lambda checked=False, c=combo: self._browse_template(c)
            )
            row_layout.addWidget(combo)
            row_layout.addWidget(browse_btn)
            return row

        if ftype in ("overlay_matrix", "overlay_matrix_update"):
            # Criteria bar (platforms + user tags, OR-combined) driving an
            # auto-selection over a base-object → overlays tree; individual
            # overlay checkboxes override.  In update mode the tree is
            # pre-checked from the selected workspace's composed set and
            # build_tokens emits add/remove diffs instead.
            from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QLabel

            update_mode = ftype == "overlay_matrix_update"

            container = QWidget()
            container.setObjectName("overlay_matrix_container")
            vlayout = QVBoxLayout(container)
            vlayout.setContentsMargins(0, 0, 0, 0)
            vlayout.setSpacing(6)

            # Load known local overlays:
            # name -> {extends, platforms, tags, deps, precedence}
            overlay_meta: dict[str, dict] = {}
            try:
                from o3de_cli.core.resolver import Resolver, ObjectNameVersion
                resolver = Resolver()
                resolver.resolve()
                for ov_name, ov in sorted(resolver.overlays.items()):
                    extends = ov.data.get("extends", "")
                    overlay_meta[ov_name] = {
                        "extends": ObjectNameVersion(extends).name if extends else "",
                        "platforms": [p for p in ov.data.get("platforms", []) or []
                                      if isinstance(p, str)],
                        "tags": [t for t in ov.data.get("user_tags", []) or []
                                 if isinstance(t, str)],
                        "deps": [ObjectNameVersion(d).name
                                 for d in (ov.data.get("dependent", {}) or {}).get("overlays", []) or []
                                 if isinstance(d, str)],
                        "precedence": ov.data.get("precedence", 0),
                    }
            except Exception:
                pass

            # -- criteria bar: platforms -------------------------------
            plat_row = QWidget()
            plat_layout = QHBoxLayout(plat_row)
            plat_layout.setContentsMargins(0, 0, 0, 0)
            plat_layout.setSpacing(10)

            cb_all = QCheckBox("All")
            cb_all.setObjectName("platform_all")
            cb_all.setChecked(not update_mode)
            cb_all.setStyleSheet("color: #EEEEEE;")
            plat_layout.addWidget(cb_all)

            known_platforms = ["Windows", "Linux", "Mac", "iOS", "Android", "Emscripten"]
            plat_checks: list[QCheckBox] = []
            for p in known_platforms:
                cb = QCheckBox(p)
                cb.setObjectName(f"platform_{p}")
                cb.setStyleSheet("color: #EEEEEE;")
                cb.setEnabled(update_mode)
                plat_layout.addWidget(cb)
                plat_checks.append(cb)
            plat_layout.addStretch()
            vlayout.addWidget(plat_row)

            # -- criteria bar: user tags -------------------------------
            all_tags = sorted({t for m in overlay_meta.values() for t in m["tags"]})
            tag_checks: list[QCheckBox] = []
            if all_tags:
                tag_row = QWidget()
                tag_layout = QHBoxLayout(tag_row)
                tag_layout.setContentsMargins(0, 0, 0, 0)
                tag_layout.setSpacing(10)
                tag_label = QLabel("Tags:")
                tag_label.setStyleSheet("color: #AAAAAA;")
                tag_layout.addWidget(tag_label)
                for t in all_tags:
                    cb = QCheckBox(t)
                    cb.setObjectName(f"tag_{t}")
                    cb.setStyleSheet("color: #EEEEEE;")
                    cb.setEnabled(update_mode or not cb_all.isChecked())
                    tag_layout.addWidget(cb)
                    tag_checks.append(cb)
                tag_layout.addStretch()
                vlayout.addWidget(tag_row)

            # -- tree: base object parents, overlay children -----------
            tree = QTreeWidget()
            tree.setObjectName("overlay_tree")
            tree.setHeaderHidden(True)
            tree.setMaximumHeight(220)

            item_by_name: dict[str, QTreeWidgetItem] = {}
            by_base: dict[str, list[str]] = {}
            for n, m in overlay_meta.items():
                by_base.setdefault(m["extends"] or "(unknown base)", []).append(n)

            for base in sorted(by_base):
                parent = QTreeWidgetItem(tree, [base])
                parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                for n in sorted(by_base[base],
                                key=lambda x: (overlay_meta[x]["precedence"], x)):
                    m = overlay_meta[n]
                    label = n
                    if m["platforms"]:
                        label += f"  [{', '.join(m['platforms'])}]"
                    if m["tags"]:
                        label += f"  {{{', '.join(m['tags'])}}}"
                    child = QTreeWidgetItem(parent, [label])
                    child.setData(0, Qt.ItemDataRole.UserRole, n)
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(
                        0,
                        Qt.CheckState.Checked if not update_mode
                        else Qt.CheckState.Unchecked,
                    )
                    item_by_name[n] = child
            tree.expandAll()
            if not overlay_meta:
                tree.setEnabled(False)
                empty = QTreeWidgetItem(tree, ["(no overlays registered)"])
            vlayout.addWidget(tree)

            hint = QLabel(
                "Platform / tag criteria auto-select overlays (OR-combined); "
                "check or uncheck individual overlays to override."
            )
            hint.setStyleSheet("color: #888888; font-size: 11px;")
            hint.setWordWrap(True)
            vlayout.addWidget(hint)

            # -- selection logic (mirrors CLI rules, OR criteria) -------
            def _auto_selection() -> set[str]:
                if cb_all.isChecked():
                    return set(overlay_meta.keys())
                sel_plats = {cb.text().lower() for cb in plat_checks if cb.isChecked()}
                sel_tags = {cb.text().lower() for cb in tag_checks if cb.isChecked()}
                dep_targets: set[str] = set()
                for m in overlay_meta.values():
                    dep_targets.update(m["deps"])
                included: set[str] = set()
                queue: list[str] = []
                for n, m in overlay_meta.items():
                    plat_match = bool(
                        sel_plats and m["platforms"]
                        and {p.lower() for p in m["platforms"]} & sel_plats
                    )
                    tag_match = bool(
                        sel_tags and m["tags"]
                        and {t.lower() for t in m["tags"]} & sel_tags
                    )
                    if plat_match or tag_match:
                        queue.append(n)
                    elif not m["platforms"] and n not in dep_targets:
                        queue.append(n)
                while queue:
                    n = queue.pop()
                    if n in included:
                        continue
                    included.add(n)
                    for dep in overlay_meta.get(n, {}).get("deps", []):
                        if dep not in included:
                            queue.append(dep)
                return included

            def _apply_auto_selection():
                auto = _auto_selection()
                for n, item in item_by_name.items():
                    item.setCheckState(
                        0,
                        Qt.CheckState.Checked if n in auto
                        else Qt.CheckState.Unchecked,
                    )

            def _on_all_toggled(checked: bool):
                for cb in plat_checks:
                    cb.setEnabled(not checked)
                for cb in tag_checks:
                    cb.setEnabled(not checked)
                _apply_auto_selection()

            cb_all.toggled.connect(_on_all_toggled)
            for cb in plat_checks + tag_checks:
                cb.toggled.connect(lambda _=False: _apply_auto_selection())

            # -- update mode: pre-check from the selected workspace -----
            container._ws_current: set[str] = set()  # type: ignore[attr-defined]

            def _load_workspace_set(ws_name: str):
                current: set[str] = set()
                try:
                    from o3de_cli.commands.workspace import (
                        _resolve_workspace_path,
                    )
                    from o3de_cli.commands.workspace import _read_workspace_meta
                    ws_path = _resolve_workspace_path(ws_name)
                    if ws_path:
                        meta = _read_workspace_meta(ws_path)
                        if meta:
                            current = set(meta.sources.overlays.keys())
                except Exception:
                    pass
                container._ws_current = current  # type: ignore[attr-defined]
                for n, item in item_by_name.items():
                    item.setCheckState(
                        0,
                        Qt.CheckState.Checked if n in current
                        else Qt.CheckState.Unchecked,
                    )

            if update_mode:
                def _wire_workspace_combo():
                    ws_widget = self._field_widgets.get("name_or_path")
                    if ws_widget is None:
                        return
                    combo = (ws_widget if isinstance(ws_widget, QComboBox)
                             else ws_widget.findChild(QComboBox))
                    if combo is None:
                        return
                    _load_workspace_set(combo.currentText())
                    combo.currentTextChanged.connect(_load_workspace_set)

                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, _wire_workspace_combo)

            # Stash for build_tokens
            container._overlay_meta = overlay_meta          # type: ignore[attr-defined]
            container._auto_selection = _auto_selection     # type: ignore[attr-defined]
            container._cb_all = cb_all                      # type: ignore[attr-defined]
            container._plat_checks = plat_checks            # type: ignore[attr-defined]
            container._tag_checks = tag_checks              # type: ignore[attr-defined]
            container._item_by_name = item_by_name          # type: ignore[attr-defined]
            container._update_mode = update_mode            # type: ignore[attr-defined]
            return container

        if ftype == "workspace":
            # Combo box of known workspaces + browse button
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            combo = QComboBox()
            combo.setEditable(True)
            combo.setObjectName("workspace_combo")
            try:
                from o3de_cli.commands.workspace import (
                    _get_registered_workspaces, _find_workspace_meta,
                )
                from o3de_cli.core import get_default_workspaces_path
                seen: set[str] = set()
                ws_root = get_default_workspaces_path()
                if ws_root.is_dir():
                    for ws_dir in sorted(ws_root.iterdir()):
                        if ws_dir.is_dir() and _find_workspace_meta(ws_dir) is not None:
                            resolved = str(ws_dir.resolve())
                            if resolved not in seen:
                                seen.add(resolved)
                                combo.addItem(ws_dir.name)
                for ws_dir in _get_registered_workspaces():
                    if ws_dir.is_dir() and _find_workspace_meta(ws_dir) is not None:
                        resolved = str(ws_dir.resolve())
                        if resolved not in seen:
                            seen.add(resolved)
                            combo.addItem(ws_dir.name)
            except Exception:
                pass
            if combo.count() == 0:
                combo.addItem("(no workspaces found)")
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            browse_btn = QPushButton("…")
            browse_btn.setObjectName("browse")
            browse_btn.setToolTip("Browse for a workspace directory")
            browse_btn.clicked.connect(
                lambda checked=False, c=combo: self._browse_workspace(c)
            )
            row_layout.addWidget(combo)
            row_layout.addWidget(browse_btn)
            return row

        # text / path → QLineEdit
        le = QLineEdit()
        placeholder = field.get("placeholder", "")
        if placeholder == "_resolve_default_":
            placeholder = self._resolve_default_path(field.get("name", ""))
        le.setPlaceholderText(placeholder)
        if prefill:
            le.setText(prefill)
        elif default:
            le.setText(default)
        return le

    # ── Helpers ────────────────────────────────────────────────────

    def _default_start_dir(self, current_text: str) -> str:
        """Return a sensible starting directory for file/folder browsers."""
        if current_text and Path(current_text).exists():
            return current_text
        from o3de_cli.core.paths import get_o3de_path
        o3de = get_o3de_path()
        if o3de.exists():
            return str(o3de)
        return str(Path.home())

    def _browse_path(self, line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(
            self, "Select Directory", self._default_start_dir(line_edit.text())
        )
        if path:
            line_edit.setText(path)

    def _browse_file(self, line_edit: QLineEdit, file_filter: str = "All Files (*)"):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", self._default_start_dir(line_edit.text()), file_filter
        )
        if path:
            line_edit.setText(path)

    def _browse_template(self, combo: QComboBox):
        path = QFileDialog.getExistingDirectory(
            self, "Select Template Directory", self._default_start_dir("")
        )
        if path:
            combo.setEditText(path)

    def _browse_workspace(self, combo: QComboBox):
        try:
            from o3de_cli.core import get_default_workspaces_path
            start = str(get_default_workspaces_path())
        except Exception:
            start = ""
        path = QFileDialog.getExistingDirectory(
            self, "Select Workspace Directory", start
        )
        if path:
            combo.setEditText(path)

    def _resolve_default_path(self, field_name: str) -> str:
        """Resolve a default path based on the command's object type."""
        try:
            from o3de_cli.core.paths import get_default_path_for_type
            from o3de_cli.core.models import ObjectType
            obj_types = self._spec.get("object_types", [])
            if obj_types:
                otype = ObjectType(obj_types[0].lower())
                return str(get_default_path_for_type(otype))
        except Exception:
            pass
        return "(default)"

    def _on_accept(self):
        # Validate required fields
        for field in self._spec.get("fields", []):
            if not field.get("required"):
                continue
            widget = self._field_widgets.get(field["name"])
            if widget is None:
                continue
            if isinstance(widget, QLineEdit) and not widget.text().strip():
                widget.setFocus()
                widget.setStyleSheet(
                    widget.styleSheet()
                    + " border-color: #FF6666;"
                )
                return
            if isinstance(widget, QComboBox) and not widget.currentText():
                widget.setFocus()
                return
            # Container widgets (e.g. template_choice)
            combo = widget.findChild(QComboBox) if not isinstance(widget, (QLineEdit, QComboBox, QCheckBox)) else None
            if combo is not None and not combo.currentText():
                combo.setFocus()
                return
        self.accept()

    # ── Public API ─────────────────────────────────────────────────

    def get_values(self) -> dict[str, str | bool]:
        """Return a dict mapping field-name → user-supplied value."""
        values: dict[str, str | bool] = {}
        for field in self._spec.get("fields", []):
            widget = self._field_widgets.get(field["name"])
            if widget is None:
                continue
            if isinstance(widget, QCheckBox):
                values[field["name"]] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[field["name"]] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                values[field["name"]] = widget.text().strip()
            else:
                # Container widgets (e.g. template_choice with combo + browse)
                combo = widget.findChild(QComboBox)
                if combo is not None:
                    values[field["name"]] = combo.currentText()
                else:
                    values[field["name"]] = ""
        return values

    def build_tokens(self) -> list[str]:
        """Build the full CLI token list for subprocess.run.

        Returns e.g. ``["gem", "create", "--name", "my-gem", "--path", "/tmp"]``
        (does NOT include ``sys.executable -m o3de_cli``).
        """
        tokens = list(self._spec["cli_args"])
        values = self.get_values()
        positional_values: list[str] = []
        # Fields that are GUI-only and not passed to the CLI
        gui_only = {"auto_register", "root_object", "overlay_selection"}
        for field in self._spec.get("fields", []):
            if field["name"] in gui_only:
                continue
            val = values.get(field["name"])
            if val is None:
                continue
            if field.get("positional"):
                # Positional arguments are appended bare at the end
                if val:
                    positional_values.append(val)
                continue
            flag_name = f"--{field['name'].replace('_', '-')}"
            if isinstance(val, bool):
                if val:
                    tokens.append(flag_name)
            elif val:
                tokens.append(flag_name)
                tokens.append(val)
        tokens.extend(positional_values)

        # Resolve overlay_selection matrix.  Create mode → --platforms /
        # --tags / --include-overlay / --exclude-overlay (only overrides
        # vs the auto-selection are emitted; the CLI selection rules
        # remain the source of truth).  Update mode → --add-overlay /
        # --remove-overlay diffs vs the workspace's current composed set.
        matrix = self._field_widgets.get("overlay_selection")
        if matrix is not None and hasattr(matrix, "_auto_selection"):
            cb_all = matrix._cb_all
            item_by_name = matrix._item_by_name

            def _checked_names() -> set[str]:
                return {
                    n for n, item in item_by_name.items()
                    if item.checkState(0) == Qt.CheckState.Checked
                }

            if matrix._update_mode:
                current = matrix._ws_current
                checked = _checked_names()
                for n in sorted(checked - current):
                    tokens.extend(["--add-overlay", n])
                for n in sorted(current - checked):
                    tokens.extend(["--remove-overlay", n])
            else:
                if not cb_all.isChecked():
                    selected = [cb.text() for cb in matrix._plat_checks
                                if cb.isChecked()]
                    if selected:
                        tokens.append("--platforms")
                        tokens.append(",".join(selected))
                    sel_tags = [cb.text() for cb in matrix._tag_checks
                                if cb.isChecked()]
                    if sel_tags:
                        tokens.append("--tags")
                        tokens.append(",".join(sel_tags))
                auto = matrix._auto_selection()
                checked = _checked_names()
                for n in sorted(checked - auto):
                    tokens.extend(["--include-overlay", n])
                for n in sorted(auto - checked):
                    tokens.extend(["--exclude-overlay", n])

        # Resolve root_object → --engine or --project with path
        if "root_object" in values and values["root_object"]:
            obj_name = values["root_object"]
            widget = self._field_widgets.get("root_object")
            if widget:
                from PySide6.QtWidgets import QRadioButton
                rb_project = widget.findChild(QRadioButton, "")
                # Check which radio is selected
                radios = widget.findChildren(QRadioButton)
                is_project = radios[0].isChecked() if radios else True
                # Resolve name to path
                try:
                    from o3de_cli.core.resolver import Resolver
                    resolver = Resolver()
                    resolver.resolve()
                    obj = resolver.objects.get(obj_name)
                    if obj and obj.path:
                        flag = "--project" if is_project else "--engine"
                        tokens.append(flag)
                        tokens.append(str(obj.path))
                except Exception:
                    pass

        return tokens


# ── Execution helper (standalone, no Qt dependency on MainWindow) ──────────

class CommandRunner:
    """Run a CLI command spec synchronously, returning (success, output)."""

    @staticmethod
    def run(tokens: list[str], *, timeout: int = 120) -> tuple[bool, str]:
        """Execute ``python -m o3de_cli <tokens>`` and return output.

        Returns:
            (True, stdout) on success, (False, error_message) on failure.
        """
        parts = [sys.executable, "-m", "o3de_cli"] + tokens
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"}
        try:
            result = subprocess.run(
                parts, capture_output=True, text=True, timeout=timeout,
                input="",  # close stdin immediately as a safety net
                env=env,
            )
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            return (result.returncode == 0, output)
        except subprocess.TimeoutExpired:
            return (False, f"⚠ Command timed out after {timeout}s.")
        except Exception as e:
            return (False, f"⚠ Error: {e}")


# ── Convenience function ───────────────────────────────────────────────────

def show_command_dialog(
    spec: dict,
    *,
    parent: QWidget | None = None,
    selected_object: Any = None,
) -> tuple[bool, list[str]] | None:
    """Show a command dialog and return (accepted, tokens) or None if cancelled."""
    dlg = CommandDialog(spec, parent=parent, selected_object=selected_object)
    if dlg.exec() == QDialog.Accepted:
        return (True, dlg.build_tokens(), dlg.get_values())
    return None
