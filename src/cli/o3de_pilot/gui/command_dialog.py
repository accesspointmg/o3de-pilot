# O3DE Pilot GUI - Command Parameter Dialog
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Reusable modal dialog that renders parameter fields for a CLI command spec
and returns a dict of user-supplied values.
"""

from __future__ import annotations

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

        # text / path → QLineEdit
        le = QLineEdit()
        le.setPlaceholderText(field.get("placeholder", ""))
        if prefill:
            le.setText(prefill)
        elif default:
            le.setText(default)
        return le

    # ── Helpers ────────────────────────────────────────────────────

    def _browse_path(self, line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(
            self, "Select Directory", line_edit.text()
        )
        if path:
            line_edit.setText(path)

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
                values[field["name"]] = ""
        return values

    def build_tokens(self) -> list[str]:
        """Build the full CLI token list for subprocess.run.

        Returns e.g. ``["gem", "create", "--name", "my-gem", "--path", "/tmp"]``
        (does NOT include ``sys.executable -m o3de_pilot``).
        """
        tokens = list(self._spec["cli_args"])
        values = self.get_values()
        positional_values: list[str] = []
        for field in self._spec.get("fields", []):
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
        return tokens


# ── Execution helper (standalone, no Qt dependency on MainWindow) ──────────

class CommandRunner:
    """Run a CLI command spec synchronously, returning (success, output)."""

    @staticmethod
    def run(tokens: list[str], *, timeout: int = 120) -> tuple[bool, str]:
        """Execute ``python -m o3de_pilot <tokens>`` and return output.

        Returns:
            (True, stdout) on success, (False, error_message) on failure.
        """
        parts = [sys.executable, "-m", "o3de_pilot"] + tokens
        try:
            result = subprocess.run(
                parts, capture_output=True, text=True, timeout=timeout
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
        return (True, dlg.build_tokens())
    return None
