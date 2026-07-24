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

        if ftype == "overlay_matrix":
            # Platform checkboxes + per-overlay override matrix.
            # Platforms drive the auto-selection; individual overlay
            # checkboxes can then be overridden by the user.
            from PySide6.QtWidgets import QListWidget, QListWidgetItem, QLabel

            container = QWidget()
            container.setObjectName("overlay_matrix_container")
            vlayout = QVBoxLayout(container)
            vlayout.setContentsMargins(0, 0, 0, 0)
            vlayout.setSpacing(6)

            # -- platform row ------------------------------------------
            plat_row = QWidget()
            plat_layout = QHBoxLayout(plat_row)
            plat_layout.setContentsMargins(0, 0, 0, 0)
            plat_layout.setSpacing(10)

            cb_all = QCheckBox("All platforms")
            cb_all.setObjectName("platform_all")
            cb_all.setChecked(True)
            cb_all.setStyleSheet("color: #EEEEEE;")
            plat_layout.addWidget(cb_all)

            known_platforms = ["Windows", "Linux", "Mac", "iOS", "Android", "Emscripten"]
            plat_checks: list[QCheckBox] = []
            for p in known_platforms:
                cb = QCheckBox(p)
                cb.setObjectName(f"platform_{p}")
                cb.setStyleSheet("color: #EEEEEE;")
                cb.setEnabled(False)  # inert while "All" is checked
                plat_layout.addWidget(cb)
                plat_checks.append(cb)
            plat_layout.addStretch()
            vlayout.addWidget(plat_row)

            # -- overlay list ------------------------------------------
            ov_list = QListWidget()
            ov_list.setObjectName("overlay_list")
            ov_list.setMaximumHeight(160)

            # Load known local overlays: name -> (platforms, overlay deps)
            overlay_meta: dict[str, tuple[list[str], list[str]]] = {}
            try:
                from o3de_cli.core.resolver import Resolver, ObjectNameVersion
                resolver = Resolver()
                resolver.resolve()
                for ov_name, ov in sorted(resolver.overlays.items()):
                    plats = [p for p in ov.data.get("platforms", []) or []
                             if isinstance(p, str)]
                    deps = [ObjectNameVersion(d).name
                            for d in (ov.data.get("dependent", {}) or {}).get("overlays", []) or []
                            if isinstance(d, str)]
                    overlay_meta[ov_name] = (plats, deps)
                    label = ov_name
                    if plats:
                        label += f"  [{', '.join(plats)}]"
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, ov_name)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                    ov_list.addItem(item)
            except Exception:
                pass
            if ov_list.count() == 0:
                ov_list.addItem("(no overlays registered)")
                ov_list.setEnabled(False)
            vlayout.addWidget(ov_list)

            hint = QLabel(
                "Platforms drive the automatic overlay selection; "
                "check/uncheck individual overlays to override."
            )
            hint.setStyleSheet("color: #888888; font-size: 11px;")
            hint.setWordWrap(True)
            vlayout.addWidget(hint)

            # -- selection logic (mirrors CLI tier rules) ---------------
            def _auto_selection() -> set[str]:
                """Compute the auto-selected overlay set for current platforms."""
                if cb_all.isChecked():
                    return set(overlay_meta.keys())
                selected = {cb.text().lower() for cb in plat_checks if cb.isChecked()}
                dep_targets: set[str] = set()
                for _n, (_p, deps) in overlay_meta.items():
                    dep_targets.update(deps)
                included: set[str] = set()
                queue: list[str] = []
                for n, (plats, _d) in overlay_meta.items():
                    if plats:
                        if {p.lower() for p in plats} & selected:
                            queue.append(n)
                    elif n not in dep_targets:
                        queue.append(n)
                while queue:
                    n = queue.pop()
                    if n in included:
                        continue
                    included.add(n)
                    for dep in overlay_meta.get(n, ([], []))[1]:
                        if dep not in included:
                            queue.append(dep)
                return included

            def _apply_auto_selection():
                auto = _auto_selection()
                for i in range(ov_list.count()):
                    item = ov_list.item(i)
                    name = item.data(Qt.ItemDataRole.UserRole)
                    if name:
                        item.setCheckState(
                            Qt.CheckState.Checked if name in auto
                            else Qt.CheckState.Unchecked
                        )

            def _on_all_toggled(checked: bool):
                for cb in plat_checks:
                    cb.setEnabled(not checked)
                _apply_auto_selection()

            cb_all.toggled.connect(_on_all_toggled)
            for cb in plat_checks:
                cb.toggled.connect(lambda _=False: _apply_auto_selection())

            # Stash for build_tokens
            container._overlay_meta = overlay_meta          # type: ignore[attr-defined]
            container._auto_selection = _auto_selection     # type: ignore[attr-defined]
            container._cb_all = cb_all                      # type: ignore[attr-defined]
            container._plat_checks = plat_checks            # type: ignore[attr-defined]
            container._ov_list = ov_list                    # type: ignore[attr-defined]
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

        # Resolve overlay_selection matrix → --platforms / --include-overlay /
        # --exclude-overlay (only overrides vs the auto-selection are emitted;
        # the CLI selection rules remain the source of truth)
        matrix = self._field_widgets.get("overlay_selection")
        if matrix is not None and hasattr(matrix, "_auto_selection"):
            cb_all = matrix._cb_all
            plat_checks = matrix._plat_checks
            ov_list = matrix._ov_list
            if not cb_all.isChecked():
                selected = [cb.text() for cb in plat_checks if cb.isChecked()]
                if selected:
                    tokens.append("--platforms")
                    tokens.append(",".join(selected))
            auto = matrix._auto_selection()
            for i in range(ov_list.count()):
                item = ov_list.item(i)
                name = item.data(Qt.ItemDataRole.UserRole)
                if not name:
                    continue
                checked = item.checkState() == Qt.CheckState.Checked
                if checked and name not in auto:
                    tokens.extend(["--include-overlay", name])
                elif not checked and name in auto:
                    tokens.extend(["--exclude-overlay", name])

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
