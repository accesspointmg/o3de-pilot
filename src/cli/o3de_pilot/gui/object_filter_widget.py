# O3DE Pilot GUI - Object Filter Widget
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Filter widget for the object catalog.
This is analogous to GemFilterWidget in the O3DE Project Manager.
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal, QSortFilterProxyModel, QModelIndex, qVersion
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QScrollArea,
    QButtonGroup, QRadioButton
)

from .object_info import ObjectOrigin, DownloadStatus
from .object_model import ObjectModel, ObjectRole
from ..core import ObjectType

# Qt 6.9+ replaces invalidateFilter() with beginFilterChange()/endFilterChange()
_QT_HAS_FILTER_CHANGE = hasattr(QSortFilterProxyModel, "beginFilterChange")


class ObjectSortFilterProxyModel(QSortFilterProxyModel):
    """
    Proxy model for filtering and sorting objects.
    """
    
    def __init__(self, source_model: ObjectModel, parent=None):
        super().__init__(parent)
        self.setSourceModel(source_model)
        
        # Filter settings
        self._search_text = ""
        self._type_filter: Optional[ObjectType] = None
        self._origin_filter: Optional[ObjectOrigin] = None
        
        # Sorting - enable dynamic sorting
        self.setSortRole(ObjectRole.DisplayName)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(True)
        self.sort(0, Qt.SortOrder.AscendingOrder)
    
    def set_search_text(self, text: str):
        """Set the search filter text."""
        self._search_text = text.lower()
        self._refilter()
    
    def set_type_filter(self, object_type: Optional[ObjectType]):
        """Set the type filter."""
        self._type_filter = object_type
        self._refilter()
    
    def set_origin_filter(self, origin: Optional[ObjectOrigin]):
        """Set the origin filter."""
        self._origin_filter = origin
        self._refilter()

    def _refilter(self):
        """Trigger re-evaluation of the filter.

        Uses beginFilterChange/endFilterChange on Qt 6.9+ (where
        invalidateFilter is deprecated), falls back to invalidateFilter
        on older versions.
        """
        if _QT_HAS_FILTER_CHANGE:
            self.beginFilterChange()
            self.endFilterChange()
        else:
            self.invalidateFilter()
    
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Determine if a row should be shown."""
        index = self.sourceModel().index(source_row, 0, source_parent)
        
        # Type filter
        if self._type_filter is not None:
            obj_type = index.data(ObjectRole.ObjectType)
            if obj_type != self._type_filter:
                return False
        
        # Origin filter
        if self._origin_filter is not None:
            origin = index.data(ObjectRole.Origin)
            if origin != self._origin_filter:
                return False
        
        # Search filter
        if self._search_text:
            name = (index.data(ObjectRole.Name) or "").lower()
            display_name = (index.data(ObjectRole.DisplayName) or "").lower()
            summary = (index.data(ObjectRole.Summary) or "").lower()
            
            if not any(self._search_text in field for field in [name, display_name, summary]):
                return False
        
        return True
    
    def get_source_index(self, proxy_index: QModelIndex) -> QModelIndex:
        """Convert proxy index to source index."""
        return self.mapToSource(proxy_index)
    
    def get_proxy_index(self, source_index: QModelIndex) -> QModelIndex:
        """Convert source index to proxy index."""
        return self.mapFromSource(source_index)


class ObjectFilterWidget(QWidget):
    """
    Widget for filtering objects in the catalog.
    
    Features:
    - Search box
    - Type filter (engines, projects, gems, etc.)
    - Origin filter (local, remote)
    - Added filter
    - Tag filters (future)
    """
    
    filterChanged = Signal()
    
    def __init__(
        self,
        proxy_model: ObjectSortFilterProxyModel,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._proxy_model = proxy_model
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)
        
        # Search box
        search_layout = QVBoxLayout()
        search_layout.setSpacing(4)
        
        search_label = QLabel("Search")
        search_label.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        search_layout.addWidget(search_label)
        
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by name...")
        self._search_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2D2D2D;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 8px;
                color: #EEEEEE;
            }
            QLineEdit:focus {
                border-color: #00A0FC;
            }
        """)
        search_layout.addWidget(self._search_edit)
        layout.addLayout(search_layout)
        
        # Separator
        layout.addWidget(self._create_separator())
        
        # Type filter
        type_layout = QVBoxLayout()
        type_layout.setSpacing(8)
        
        type_label = QLabel("Object Type")
        type_label.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        type_layout.addWidget(type_label)
        
        self._type_group = QButtonGroup(self)
        self._type_group.setExclusive(True)
        
        # All types option
        all_radio = QRadioButton("All Types")
        all_radio.setChecked(True)
        all_radio.setStyleSheet(self._radio_style())
        self._type_group.addButton(all_radio, 0)
        type_layout.addWidget(all_radio)
        
        # Individual type options (skip MANIFEST — only one manifest exists)
        for i, obj_type in enumerate(ObjectType, start=1):
            if obj_type == ObjectType.MANIFEST:
                continue
            radio = QRadioButton(obj_type.value.capitalize() + "s")
            radio.setStyleSheet(self._radio_style())
            radio.setProperty("object_type", obj_type)
            self._type_group.addButton(radio, i)
            type_layout.addWidget(radio)
        
        layout.addLayout(type_layout)
        
        # Separator
        layout.addWidget(self._create_separator())
        
        # Origin filter
        origin_layout = QVBoxLayout()
        origin_layout.setSpacing(8)
        
        origin_label = QLabel("Origin")
        origin_label.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        origin_layout.addWidget(origin_label)
        
        self._origin_group = QButtonGroup(self)
        self._origin_group.setExclusive(True)
        
        all_origin = QRadioButton("All")
        all_origin.setChecked(True)
        all_origin.setStyleSheet(self._radio_style())
        self._origin_group.addButton(all_origin, 0)
        origin_layout.addWidget(all_origin)
        
        local_radio = QRadioButton("Local")
        local_radio.setStyleSheet(self._radio_style())
        local_radio.setProperty("origin", ObjectOrigin.LOCAL)
        self._origin_group.addButton(local_radio, 1)
        origin_layout.addWidget(local_radio)
        
        remote_radio = QRadioButton("Remote")
        remote_radio.setStyleSheet(self._radio_style())
        remote_radio.setProperty("origin", ObjectOrigin.REMOTE)
        self._origin_group.addButton(remote_radio, 2)
        origin_layout.addWidget(remote_radio)
        
        layout.addLayout(origin_layout)
        
        layout.addStretch()
        
        # Add stretch at bottom
        layout.addStretch()
        
        # Style the widget
        self.setStyleSheet("""
            QWidget {
                background-color: #1A1A1A;
            }
        """)
    
    def _create_separator(self) -> QFrame:
        """Create a horizontal separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #333333;")
        line.setFixedHeight(1)
        return line
    
    def _radio_style(self) -> str:
        """Get the style for radio buttons."""
        return """
            QRadioButton {
                color: #EEEEEE;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #555555;
                border-radius: 7px;
                background-color: #2D2D2D;
            }
            QRadioButton::indicator:checked {
                background-color: #00A0FC;
                border-color: #00A0FC;
            }
        """
    
    def _connect_signals(self):
        """Connect UI signals to handlers."""
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._type_group.idClicked.connect(self._on_type_changed)
        self._origin_group.idClicked.connect(self._on_origin_changed)

    
    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._proxy_model.set_search_text(text)
        self.filterChanged.emit()
    
    def _on_type_changed(self, button_id: int):
        """Handle type filter change."""
        if button_id == 0:
            self._proxy_model.set_type_filter(None)
        else:
            button = self._type_group.button(button_id)
            obj_type = button.property("object_type")
            self._proxy_model.set_type_filter(obj_type)
        self.filterChanged.emit()
    
    def _on_origin_changed(self, button_id: int):
        """Handle origin filter change."""
        if button_id == 0:
            self._proxy_model.set_origin_filter(None)
        else:
            button = self._origin_group.button(button_id)
            origin = button.property("origin")
            self._proxy_model.set_origin_filter(origin)
        self.filterChanged.emit()
    
    def reset_filters(self):
        """Reset all filters to default."""
        self._search_edit.clear()
        self._type_group.button(0).setChecked(True)
        self._origin_group.button(0).setChecked(True)
        self._proxy_model.set_search_text("")
        self._proxy_model.set_type_filter(None)
        self._proxy_model.set_origin_filter(None)
        self.filterChanged.emit()
