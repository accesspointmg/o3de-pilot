# O3DE Pilot GUI - Object Catalog Screen
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Main catalog screen for browsing O3DE objects.
This is analogous to GemCatalogScreen in the O3DE Project Manager.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QModelIndex
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter, QStackedWidget, QSizePolicy, QMenu
)

from .object_model import ObjectModel
from .object_filter_widget import ObjectFilterWidget, ObjectSortFilterProxyModel
from .object_list_view import ObjectListView
from .object_inspector import ObjectInspector
from .object_info import ObjectInfo
from o3de_cli.core import ObjectType
from .command_specs import COMMAND_SPECS, TOOLBAR_GROUPS, get_commands_for_group


class ObjectCatalogHeader(QWidget):
    """Header widget for the catalog screen."""
    
    refreshClicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        
        # Title
        title = QLabel("Object Catalog")
        title.setStyleSheet("color: #EEEEEE; font-size: 11pt; font-weight: bold;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Count label
        self._count_label = QLabel("0 objects")
        self._count_label.setStyleSheet("color: #888888; font-size: 9pt;")
        layout.addWidget(self._count_label)
        
        # Refresh button
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #3D3D3D;
            }
        """)
        self._refresh_button.clicked.connect(self.refreshClicked)
        layout.addWidget(self._refresh_button)
        
        # Scoped style – use objectName to avoid cascading border to children
        self.setObjectName("catalogHeader")
        self.setFixedHeight(28)
        self.setStyleSheet("#catalogHeader { background-color: #1A1A1A; border-bottom: 1px solid #333333; }")
    
    def set_count(self, count: int, total: int = None):
        """Update the object count display."""
        if total is not None and total != count:
            self._count_label.setText(f"{count} of {total} objects")
        else:
            self._count_label.setText(f"{count} object{'s' if count != 1 else ''}")
    
    def set_refresh_enabled(self, enabled: bool):
        """Enable or disable the refresh button (for offline mode)."""
        self._refresh_button.setEnabled(enabled)
        if not enabled:
            self._refresh_button.setToolTip("Refresh disabled - no internet connection")
        else:
            self._refresh_button.setToolTip("")


class ObjectCatalogScreen(QWidget):
    """
    Main catalog screen for browsing and managing O3DE objects.
    
    Layout:
    +------------------+------------------------+------------------+
    |     Header       |                        |                  |
    +------------------+------------------------+------------------+
    |                  |                        |                  |
    |    Filters       |      Object List       |    Inspector     |
    |   (240px)        |      (stretch)         |    (240px)       |
    |                  |                        |                  |
    +------------------+------------------------+------------------+
    """
    
    # Signals
    objectSelected = Signal(ObjectInfo)
    objectDownloaded = Signal(ObjectInfo)
    refreshRequested = Signal()
    commandRequested = Signal(dict, object)  # (command_spec, selected_object_or_None)
    unregisterRequested = Signal(object)       # ObjectInfo — direct unregister
    
    SIDE_PANEL_WIDTH = 300
    
    def __init__(
        self,
        read_only: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._read_only = read_only
        
        # Create model
        self._model = ObjectModel(self)
        self._proxy_model = ObjectSortFilterProxyModel(self._model, self)
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """Set up the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        self._header = ObjectCatalogHeader()
        main_layout.addWidget(self._header)
        
        # Command toolbar
        self._toolbar = self._create_command_toolbar()
        main_layout.addWidget(self._toolbar)
        
        # Content area – use a splitter so panels can be resized
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #444444;
            }
        """)
        
        # Left panel - Filters
        self._filter_widget = ObjectFilterWidget(self._proxy_model)
        self._filter_widget.setMinimumWidth(160)
        self._splitter.addWidget(self._filter_widget)
        
        # Center - Object list
        self._list_view = ObjectListView(
            self._proxy_model,
            read_only=self._read_only,
            parent=self
        )
        self._list_view.setMinimumWidth(400)
        self._list_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._splitter.addWidget(self._list_view)
        
        # Right panel - Inspector
        self._inspector = ObjectInspector(self._model, self._read_only)
        self._inspector.setMinimumWidth(280)
        self._splitter.addWidget(self._inspector)
        
        # Set initial sizes: filter, list, inspector
        self._splitter.setSizes([self.SIDE_PANEL_WIDTH, 600, self.SIDE_PANEL_WIDTH])
        # Allow the center list to stretch; side panels keep their size
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        
        # Prevent panels from collapsing
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._splitter.setCollapsible(2, False)
        
        main_layout.addWidget(self._splitter)
        
        # Overall style
        self.setStyleSheet("background-color: #222222;")
    
    def _create_command_toolbar(self) -> QWidget:
        """Build the dropdown-button toolbar for CLI commands."""
        bar = QWidget()
        bar.setObjectName("commandToolbar")
        bar.setFixedHeight(24)
        bar.setStyleSheet(
            "#commandToolbar { background-color: #1E1E1E; border-bottom: 1px solid #333333; }"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 1px 8px;
                font-size: 8pt;
                min-height: 18px;
                max-height: 20px;
            }
            QPushButton:hover { background-color: #3A3A3A; }
            QPushButton::menu-indicator { width: 0; height: 0; }
        """
        menu_style = """
            QMenu {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
            }
            QMenu::item:selected {
                background-color: #0078D4;
            }
            QMenu::separator {
                height: 1px;
                background: #444444;
                margin: 4px 8px;
            }
        """

        for group in TOOLBAR_GROUPS:
            btn = QPushButton(f"{group['label']} ▾")
            btn.setToolTip(group.get("tooltip", ""))
            btn.setStyleSheet(btn_style)

            menu = QMenu(self)
            menu.setStyleSheet(menu_style)

            specs = get_commands_for_group(group["id"])
            for spec in specs:
                if spec is None:
                    menu.addSeparator()
                elif "submenu" in spec:
                    # Nested submenu (hover to expand)
                    sub_menu = menu.addMenu(spec["submenu"])
                    sub_menu.setStyleSheet(menu_style)
                    for sub_spec in spec.get("items", []):
                        if sub_spec is None:
                            sub_menu.addSeparator()
                        else:
                            sub_action = sub_menu.addAction(sub_spec["title"])
                            sub_action.setToolTip(sub_spec.get("description", ""))
                            sub_action.triggered.connect(
                                lambda _checked=False, s=sub_spec: self._on_toolbar_command(s)
                            )
                else:
                    action = menu.addAction(spec["title"])
                    action.setToolTip(spec.get("description", ""))
                    # Capture spec in closure
                    action.triggered.connect(
                        lambda _checked=False, s=spec: self._on_toolbar_command(s)
                    )

            btn.setMenu(menu)
            row.addWidget(btn)

        row.addStretch(1)
        return bar

    def _on_toolbar_command(self, spec: dict):
        """Emit commandRequested with the selected object (if any)."""
        selected_obj = self._get_selected_object()
        self.commandRequested.emit(spec, selected_obj)

    def _get_selected_object(self) -> ObjectInfo | None:
        """Return the currently selected ObjectInfo, or None."""
        indexes = self._list_view.selectionModel().selectedIndexes()
        if indexes:
            source_index = self._proxy_model.mapToSource(indexes[0])
            return self._model.get_object_info(source_index)
        return None

    def _create_vertical_separator(self) -> QFrame:
        """Create a vertical separator."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("background-color: #333333;")
        line.setFixedWidth(1)
        return line
    
    def _connect_signals(self):
        """Connect internal signals."""
        # Header
        self._header.refreshClicked.connect(self._on_refresh_requested)
        
        # Filter
        self._filter_widget.filterChanged.connect(self._update_count)
        
        # List view selection
        self._list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        # Inspector actions
        self._inspector.downloadClicked.connect(self._on_download_clicked)
        
        # Command requests (from list view context menu and inspector actions)
        self._list_view.commandRequested.connect(self.commandRequested)
        self._inspector.commandRequested.connect(self.commandRequested)
        self._inspector.unregisterRequested.connect(self.unregisterRequested)
    
    def _on_selection_changed(self, selected, deselected):
        """Handle selection change in list view."""
        indexes = selected.indexes()
        if indexes:
            # Convert proxy index to source index
            source_index = self._proxy_model.mapToSource(indexes[0])
            self._inspector.update_from_index(source_index)
            
            info = self._model.get_object_info(source_index)
            if info:
                self.objectSelected.emit(info)
        else:
            self._inspector.update_from_index(QModelIndex())
    
    def _on_download_clicked(self, index: QModelIndex):
        """Handle download button click in inspector."""
        if index.isValid():
            info = self._model.get_object_info(index)
            if info:
                self.objectDownloaded.emit(info)
    
    def _on_refresh_requested(self):
        """Handle refresh button click."""
        self.refreshRequested.emit()
    
    def _update_count(self):
        """Update the object count in header."""
        visible = self._proxy_model.rowCount()
        total = self._model.rowCount()
        self._header.set_count(visible, total)
    
    @property
    def model(self) -> ObjectModel:
        """Get the object model."""
        return self._model
    
    @property
    def proxy_model(self) -> ObjectSortFilterProxyModel:
        """Get the proxy model."""
        return self._proxy_model
    
    def add_object(self, info: ObjectInfo):
        """Add an object to the catalog."""
        self._model.add_object(info)
        self._update_count()
    
    def add_objects(self, infos: list[ObjectInfo]):
        """Add multiple objects to the catalog."""
        self._model.add_objects(infos)
        self._update_count()
    
    def clear(self):
        """Clear all objects from the catalog."""
        self._model.clear_all()
        self._update_count()
    
    def select_object(self, name: str) -> bool:
        """Select an object by name."""
        return self._list_view.select_object(name)
    
    def set_type_filter(self, object_type: Optional[ObjectType]):
        """Set the type filter programmatically."""
        self._proxy_model.set_type_filter(object_type)
        self._update_count()
    
    def reset_filters(self):
        """Reset all filters."""
        self._filter_widget.reset_filters()
    
    def set_refresh_enabled(self, enabled: bool):
        """Enable or disable the refresh button (for offline mode)."""
        self._header.set_refresh_enabled(enabled)
    
    def set_download_enabled(self, enabled: bool):
        """Enable or disable download functionality (for offline mode)."""
        self._inspector.set_download_enabled(enabled)
    
    def get_selected_version(self) -> str | None:
        """Get the version selected in the inspector dropdown."""
        return self._inspector.get_selected_version()
    
    def get_selected_method(self) -> str | None:
        """Get the download method selected in the inspector dropdown."""
        return self._inspector.get_selected_method()
    
    def get_selected_format(self) -> str | None:
        """Get the archive format selected in the inspector dropdown."""
        return self._inspector.get_selected_format()
    
    def get_download_urls(self) -> dict:
        """Get the download URLs for the selected version/method/format."""
        return self._inspector.get_download_urls()
