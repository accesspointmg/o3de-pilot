# O3DE Pilot GUI - Settings Dialog
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Settings dialog for editing manifest preferences.
"""

import json
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QGroupBox,
    QDialogButtonBox, QFileDialog, QWidget, QLabel
)


def load_countries() -> list[tuple[str, str]]:
    """Load countries from data/countries.json."""
    countries_file = Path(__file__).parent.parent / "data" / "countries.json"
    if countries_file.exists():
        with open(countries_file, encoding="utf-8") as f:
            data = json.load(f)
            return [(c["code"], c["name"]) for c in data]
    # Fallback
    return [("US", "United States"), ("CA", "Canada"), ("GB", "United Kingdom")]


class PathEditor(QWidget):
    """Widget for editing a path with browse button."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self._edit = QLineEdit()
        self._edit.setMinimumWidth(300)
        layout.addWidget(self._edit, 1)
        
        self._browse = QPushButton("Browse...")
        self._browse.clicked.connect(self._on_browse)
        layout.addWidget(self._browse)
    
    def _on_browse(self):
        """Open folder browser dialog."""
        current = self._edit.text()
        
        # Convert POSIX slashes to Windows for path checking
        if current:
            current_path = Path(current.replace("/", "\\"))
            if current_path.exists():
                start_dir = str(current_path)
            elif current_path.parent.exists():
                # If path doesn't exist, try parent
                start_dir = str(current_path.parent)
            else:
                start_dir = str(Path.home())
        else:
            start_dir = str(Path.home())
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            start_dir
        )
        if folder:
            # Use forward slashes (POSIX style)
            self._edit.setText(folder.replace("\\", "/"))
    
    def text(self) -> str:
        return self._edit.text()
    
    def setText(self, text: str):
        self._edit.setText(text)


class SettingsDialog(QDialog):
    """Dialog for editing manifest settings."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(550)
        
        self._setup_ui()
        self._apply_styles()
    
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Country section
        country_group = QGroupBox("Region")
        country_layout = QFormLayout(country_group)
        
        self._country_combo = QComboBox()
        for code, name in load_countries():
            self._country_combo.addItem(f"{name} ({code})", code)
        country_layout.addRow("Country:", self._country_combo)
        
        layout.addWidget(country_group)
        
        # Default paths section
        paths_group = QGroupBox("Default Paths")
        paths_layout = QFormLayout(paths_group)
        paths_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        
        self._engines_path = PathEditor()
        paths_layout.addRow("Engines:", self._engines_path)
        
        self._projects_path = PathEditor()
        paths_layout.addRow("Projects:", self._projects_path)
        
        self._gems_path = PathEditor()
        paths_layout.addRow("Gems:", self._gems_path)
        
        self._templates_path = PathEditor()
        paths_layout.addRow("Templates:", self._templates_path)
        
        self._repos_path = PathEditor()
        paths_layout.addRow("Repos:", self._repos_path)
        
        self._overlays_path = PathEditor()
        paths_layout.addRow("Overlays:", self._overlays_path)
        
        self._third_party_path = PathEditor()
        paths_layout.addRow("Third Party:", self._third_party_path)
        
        layout.addWidget(paths_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _apply_styles(self):
        """Apply dark theme styles."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D30;
                color: #FFFFFF;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3F3F46;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #FFFFFF;
            }
            QLabel {
                color: #CCCCCC;
            }
            QLineEdit {
                background-color: #1E1E1E;
                border: 1px solid #3F3F46;
                border-radius: 3px;
                padding: 4px 8px;
                color: #FFFFFF;
            }
            QLineEdit:focus {
                border-color: #007ACC;
            }
            QComboBox {
                background-color: #1E1E1E;
                border: 1px solid #3F3F46;
                border-radius: 3px;
                padding: 4px 8px;
                padding-right: 20px;
                color: #FFFFFF;
                min-width: 200px;
            }
            QComboBox QAbstractItemView {
                background-color: #1E1E1E;
                border: 1px solid #3F3F46;
                color: #FFFFFF;
                selection-background-color: #094771;
            }
            QPushButton {
                background-color: #0E639C;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QDialogButtonBox QPushButton {
                min-width: 80px;
            }
        """)
    
    def load_from_manifest(self, manifest_data: dict):
        """Load settings from manifest dictionary."""
        # Country
        country = manifest_data.get("country", {})
        country_code = country.get("code", "US")
        
        # Find and select the country
        for i in range(self._country_combo.count()):
            if self._country_combo.itemData(i) == country_code:
                self._country_combo.setCurrentIndex(i)
                break
        
        # Default paths
        defaults = manifest_data.get("default", {})
        self._engines_path.setText(defaults.get("engines_path", ""))
        self._projects_path.setText(defaults.get("projects_path", ""))
        self._gems_path.setText(defaults.get("gems_path", ""))
        self._templates_path.setText(defaults.get("templates_path", ""))
        self._repos_path.setText(defaults.get("repos_path", ""))
        self._overlays_path.setText(defaults.get("overlays_path", ""))
        self._third_party_path.setText(defaults.get("third_party_path", ""))
    
    def save_to_manifest(self, manifest_data: dict) -> dict:
        """Update manifest dictionary with current settings."""
        # Country
        manifest_data["country"] = {
            "code": self._country_combo.currentData()
        }
        
        # Default paths
        manifest_data["default"] = {
            "engines_path": self._engines_path.text(),
            "projects_path": self._projects_path.text(),
            "gems_path": self._gems_path.text(),
            "templates_path": self._templates_path.text(),
            "repos_path": self._repos_path.text(),
            "overlays_path": self._overlays_path.text(),
            "third_party_path": self._third_party_path.text(),
        }
        
        return manifest_data
