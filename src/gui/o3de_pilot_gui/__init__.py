# O3DE Pilot GUI - Qt6 Package
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Qt6 GUI for O3DE Pilot.

This provides a graphical interface similar to the O3DE Project Manager
but generalized for all object types (engines, projects, gems, templates, repos, overlays).

Components:
    ObjectInfo - Data class for object information
    ObjectModel - Qt model for object data
    ObjectDelegate - Custom item rendering
    ObjectListView - List view display
    ObjectInspector - Details panel
    ObjectFilterWidget - Search/filter controls
    ObjectCatalogScreen - Main catalog screen
    MainWindow - Main application window
"""

from importlib.metadata import PackageNotFoundError, version as _dist_version

try:
    __version__ = _dist_version("o3de-pilot")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

from .object_info import ObjectInfo, ObjectOrigin, DownloadStatus
from .object_model import ObjectModel, ObjectRole
from .object_delegate import ObjectItemDelegate
from .object_list_view import ObjectListView
from .object_inspector import ObjectInspector
from .object_filter_widget import ObjectFilterWidget
from .object_catalog_screen import ObjectCatalogScreen
from .object_tree_screen import ObjectTreeScreen
from .main_window import MainWindow

__all__ = [
    "__version__",
    "ObjectInfo",
    "ObjectOrigin",
    "DownloadStatus",
    "ObjectModel",
    "ObjectRole",
    "ObjectItemDelegate",
    "ObjectListView",
    "ObjectInspector",
    "ObjectFilterWidget",
    "ObjectCatalogScreen",
    "ObjectTreeScreen",
    "MainWindow",
]
