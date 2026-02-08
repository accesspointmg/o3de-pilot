# O3DE Pilot GUI - Object Model
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Qt model for O3DE objects in the catalog.
This is analogous to GemModel in the O3DE Project Manager.
"""

from enum import IntEnum
from typing import Optional, Any
from PySide6.QtCore import Qt, QModelIndex, QPersistentModelIndex, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import QApplication

from .object_info import ObjectInfo, ObjectOrigin, DownloadStatus
from ..core import ObjectType


class ObjectRole(IntEnum):
    """Custom data roles for the object model."""
    # Core identity
    Name = Qt.ItemDataRole.UserRole
    DisplayName = Qt.ItemDataRole.UserRole + 1
    ObjectType = Qt.ItemDataRole.UserRole + 2
    Version = Qt.ItemDataRole.UserRole + 3
    
    # Status
    IsAdded = Qt.ItemDataRole.UserRole + 10
    IsAddedDependency = Qt.ItemDataRole.UserRole + 11
    WasPreviouslyAdded = Qt.ItemDataRole.UserRole + 12
    DownloadStatus = Qt.ItemDataRole.UserRole + 13
    DownloadProgress = Qt.ItemDataRole.UserRole + 14  # 0-100 progress value
    
    # Origin
    Origin = Qt.ItemDataRole.UserRole + 20
    OriginUrl = Qt.ItemDataRole.UserRole + 21
    Path = Qt.ItemDataRole.UserRole + 22
    
    # Display info
    Summary = Qt.ItemDataRole.UserRole + 30
    Creator = Qt.ItemDataRole.UserRole + 31
    
    # Full object info
    ObjectInfo = Qt.ItemDataRole.UserRole + 100


class ObjectModel(QStandardItemModel):
    """
    Model for O3DE objects (engines, projects, gems, templates, repos, overlays).
    
    Signals:
        objectStatusChanged: Emitted when an object's status changes
        selectionChanged: Emitted when selection changes
    """
    
    objectStatusChanged = Signal(str, int)  # name, num_changed_deps
    dependencyStatusChanged = Signal(str)   # name
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._name_to_index: dict[str, QPersistentModelIndex] = {}
        self._type_filter: Optional[ObjectType] = None
    
    def add_object(self, info: ObjectInfo) -> QPersistentModelIndex:
        """
        Add an object to the model.
        
        Args:
            info: Object information to add
            
        Returns:
            Persistent index to the added item
        """
        # Create item
        item = QStandardItem()
        item.setEditable(False)
        
        # Set all data roles
        item.setData(info.name, ObjectRole.Name)
        item.setData(info.display_name, ObjectRole.DisplayName)
        item.setData(info.object_type, ObjectRole.ObjectType)
        item.setData(info.version, ObjectRole.Version)
        item.setData(info.is_added, ObjectRole.IsAdded)
        item.setData(False, ObjectRole.IsAddedDependency)
        item.setData(info.is_added, ObjectRole.WasPreviouslyAdded)
        item.setData(info.download_status, ObjectRole.DownloadStatus)
        item.setData(info.download_progress, ObjectRole.DownloadProgress)
        item.setData(info.origin, ObjectRole.Origin)
        item.setData(info.origin_url, ObjectRole.OriginUrl)
        item.setData(str(info.path) if info.path else "", ObjectRole.Path)
        item.setData(info.summary, ObjectRole.Summary)
        item.setData(info.creator, ObjectRole.Creator)
        item.setData(info, ObjectRole.ObjectInfo)
        
        # Set display role
        item.setData(info.display_name, Qt.ItemDataRole.DisplayRole)
        
        # Add to model
        self.appendRow(item)
        
        # Create persistent index
        index = QPersistentModelIndex(self.indexFromItem(item))
        
        # Map name to index for quick lookup
        key = f"{info.object_type.value}:{info.name}:{info.version}"
        self._name_to_index[key] = index
        
        return index
    
    def add_objects(self, infos: list[ObjectInfo], update_existing: bool = False) -> list[QPersistentModelIndex]:
        """
        Add multiple objects to the model.
        
        Args:
            infos: List of object information to add
            update_existing: If True, update existing objects instead of skipping
            
        Returns:
            List of persistent indices to added items
        """
        indices = []
        for info in infos:
            key = f"{info.object_type.value}:{info.name}:{info.version}"
            if key in self._name_to_index:
                if update_existing:
                    self.update_object(self._name_to_index[key], info)
                    indices.append(self._name_to_index[key])
            else:
                indices.append(self.add_object(info))
        return indices
    
    def update_object(self, index: QModelIndex, info: ObjectInfo):
        """Update an existing object with new information."""
        if not index.isValid():
            return
        
        item = self.itemFromIndex(index)
        if not item:
            return
        
        # Update all data roles
        item.setData(info.name, ObjectRole.Name)
        item.setData(info.display_name, ObjectRole.DisplayName)
        item.setData(info.object_type, ObjectRole.ObjectType)
        item.setData(info.version, ObjectRole.Version)
        item.setData(info.download_status, ObjectRole.DownloadStatus)
        item.setData(info.origin, ObjectRole.Origin)
        item.setData(info.origin_url, ObjectRole.OriginUrl)
        item.setData(str(info.path) if info.path else "", ObjectRole.Path)
        item.setData(info.summary, ObjectRole.Summary)
        item.setData(info.creator, ObjectRole.Creator)
        item.setData(info, ObjectRole.ObjectInfo)
        item.setData(info.display_name, Qt.ItemDataRole.DisplayRole)
    
    def remove_object(self, index: QModelIndex):
        """Remove an object from the model."""
        if not index.isValid():
            return
        
        # Remove from name map
        info = self.get_object_info(index)
        if info:
            key = f"{info.object_type.value}:{info.name}:{info.version}"
            self._name_to_index.pop(key, None)
        
        self.removeRow(index.row())
    
    def clear_all(self):
        """Clear all objects from the model."""
        self._name_to_index.clear()
        self.clear()
    
    def find_by_name(self, object_type: ObjectType, name: str, version: str = "") -> Optional[QPersistentModelIndex]:
        """
        Find an object by type, name, and optional version.
        
        Args:
            object_type: Type of object to find
            name: Object name
            version: Optional version string
            
        Returns:
            Persistent index if found, None otherwise
        """
        # Try exact match first
        if version:
            key = f"{object_type.value}:{name}:{version}"
            if key in self._name_to_index:
                return self._name_to_index[key]
        
        # Search for any version
        prefix = f"{object_type.value}:{name}:"
        for key, index in self._name_to_index.items():
            if key.startswith(prefix):
                return index
        
        return None
    
    @staticmethod
    def get_object_info(index: QModelIndex) -> Optional[ObjectInfo]:
        """Get the ObjectInfo for a model index."""
        if not index.isValid():
            return None
        return index.data(ObjectRole.ObjectInfo)
    
    @staticmethod
    def get_name(index: QModelIndex) -> str:
        """Get the name for a model index."""
        if not index.isValid():
            return ""
        return index.data(ObjectRole.Name) or ""
    
    @staticmethod
    def get_display_name(index: QModelIndex) -> str:
        """Get the display name for a model index."""
        if not index.isValid():
            return ""
        return index.data(ObjectRole.DisplayName) or ""
    
    @staticmethod
    def get_object_type(index: QModelIndex) -> Optional[ObjectType]:
        """Get the object type for a model index."""
        if not index.isValid():
            return None
        return index.data(ObjectRole.ObjectType)
    
    @staticmethod
    def get_version(index: QModelIndex) -> str:
        """Get the version for a model index."""
        if not index.isValid():
            return ""
        return index.data(ObjectRole.Version) or ""
    
    @staticmethod
    def is_added(index: QModelIndex) -> bool:
        """Check if the object is added."""
        if not index.isValid():
            return False
        return bool(index.data(ObjectRole.IsAdded))
    
    @staticmethod
    def is_added_dependency(index: QModelIndex) -> bool:
        """Check if the object is added as a dependency."""
        if not index.isValid():
            return False
        return bool(index.data(ObjectRole.IsAddedDependency))
    
    @staticmethod
    def get_download_status(index: QModelIndex) -> DownloadStatus:
        """Get the download status for a model index."""
        if not index.isValid():
            return DownloadStatus.UNKNOWN
        return index.data(ObjectRole.DownloadStatus) or DownloadStatus.UNKNOWN
    
    @staticmethod
    def set_is_added(model: QStandardItemModel, index: QModelIndex, is_added: bool):
        """Set whether an object is added."""
        if not index.isValid():
            return
        item = model.itemFromIndex(index)
        if item:
            item.setData(is_added, ObjectRole.IsAdded)
    
    @staticmethod
    def set_download_status(model: QStandardItemModel, index: QModelIndex, status: DownloadStatus):
        """Set the download status for an object."""
        if not index.isValid():
            return
        item = model.itemFromIndex(index)
        if item:
            item.setData(status, ObjectRole.DownloadStatus)
    
    @staticmethod
    def set_download_progress(model: QStandardItemModel, index: QModelIndex, progress: int):
        """Set the download progress (0-100) for an object."""
        if not index.isValid():
            return
        item = model.itemFromIndex(index)
        if item:
            item.setData(progress, ObjectRole.DownloadProgress)
    
    def get_objects_by_type(self, object_type: ObjectType) -> list[ObjectInfo]:
        """Get all objects of a specific type."""
        result = []
        for row in range(self.rowCount()):
            index = self.index(row, 0)
            obj_type = self.get_object_type(index)
            if obj_type == object_type:
                info = self.get_object_info(index)
                if info:
                    result.append(info)
        return result
    
    def get_added_objects(self, include_dependencies: bool = False) -> list[ObjectInfo]:
        """Get all objects that are marked as added."""
        result = []
        for row in range(self.rowCount()):
            index = self.index(row, 0)
            if self.is_added(index):
                info = self.get_object_info(index)
                if info:
                    result.append(info)
            elif include_dependencies and self.is_added_dependency(index):
                info = self.get_object_info(index)
                if info:
                    result.append(info)
        return result
    
    def total_count(self) -> int:
        """Get total number of objects."""
        return self.rowCount()
    
    def count_by_type(self, object_type: ObjectType) -> int:
        """Get count of objects of a specific type."""
        count = 0
        for row in range(self.rowCount()):
            index = self.index(row, 0)
            if self.get_object_type(index) == object_type:
                count += 1
        return count
