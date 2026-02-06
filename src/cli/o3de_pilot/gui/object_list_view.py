# O3DE Pilot GUI - Object List View
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
List view for displaying O3DE objects in the catalog.
This is analogous to GemListView in the O3DE Project Manager.
"""

from typing import Optional
from PySide6.QtCore import Qt, QModelIndex, Signal, QItemSelectionModel
from PySide6.QtWidgets import (
    QListView, QWidget, QVBoxLayout, QAbstractItemView
)

from .object_delegate import ObjectItemDelegate
from .object_model import ObjectModel


class ObjectListView(QListView):
    """
    List view for displaying O3DE objects.
    
    Features:
    - Custom item delegate for rich rendering
    - Keyboard navigation
    - Single/multi selection
    - Scroll to item support
    """
    
    objectDoubleClicked = Signal(QModelIndex)
    
    def __init__(
        self,
        model: ObjectModel,
        selection_model: Optional[QItemSelectionModel] = None,
        read_only: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._model = model
        self._read_only = read_only
        
        # Setup view
        self.setModel(model)
        
        # Use custom selection model if provided
        if selection_model:
            self.setSelectionModel(selection_model)
        
        # Custom delegate
        self._delegate = ObjectItemDelegate(self, read_only)
        self.setItemDelegate(self._delegate)
        
        # View settings
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        
        # Selection settings
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Mouse tracking for hover effects
        self.setMouseTracking(True)
        
        # Style
        self.setStyleSheet("""
            QListView {
                background-color: #222222;
                border: none;
                outline: none;
            }
            QListView::item {
                border: none;
                padding: 0px;
            }
            QListView::item:selected {
                background-color: transparent;
            }
            QListView::item:hover {
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #2D2D2D;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 30px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Connect signals
        self.doubleClicked.connect(self._on_double_clicked)
    
    def _on_double_clicked(self, index: QModelIndex):
        """Handle double click on an item."""
        if index.isValid():
            self.objectDoubleClicked.emit(index)
    
    def select_object(self, name: str) -> bool:
        """
        Select an object by name.
        
        Args:
            name: Object name to select
            
        Returns:
            True if object was found and selected
        """
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            if self._model.get_name(index) == name:
                self.setCurrentIndex(index)
                self.scrollTo(index)
                return True
        return False
    
    def scroll_to_object(self, name: str):
        """Scroll to an object by name."""
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            if self._model.get_name(index) == name:
                self.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
                break
    
    def clear_selection(self):
        """Clear the current selection."""
        self.clearSelection()
        self.setCurrentIndex(QModelIndex())


class ObjectListWidget(QWidget):
    """
    Widget containing object list view with optional header.
    """
    
    selectionChanged = Signal(QModelIndex)
    objectDoubleClicked = Signal(QModelIndex)
    
    def __init__(
        self,
        model: ObjectModel,
        read_only: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._model = model
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create list view
        self._list_view = ObjectListView(model, read_only=read_only, parent=self)
        layout.addWidget(self._list_view)
        
        # Connect signals
        self._list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._list_view.objectDoubleClicked.connect(self.objectDoubleClicked)
    
    def _on_selection_changed(self, selected, deselected):
        """Handle selection change in the list view."""
        indexes = selected.indexes()
        if indexes:
            self.selectionChanged.emit(indexes[0])
        else:
            self.selectionChanged.emit(QModelIndex())
    
    @property
    def list_view(self) -> ObjectListView:
        """Get the underlying list view."""
        return self._list_view
    
    def selected_index(self) -> QModelIndex:
        """Get the currently selected index."""
        return self._list_view.currentIndex()
