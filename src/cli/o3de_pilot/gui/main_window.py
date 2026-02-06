# O3DE Pilot GUI - Main Window
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Main application window for O3DE Pilot GUI.
"""

from typing import Optional
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QSize
from PySide6.QtGui import QAction, QIcon, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget,
    QMenuBar, QMenu, QToolBar, QStatusBar, QMessageBox,
    QFileDialog, QApplication
)

from .object_catalog_screen import ObjectCatalogScreen
from .object_info import ObjectInfo, ObjectOrigin, DownloadStatus
from ..core import ObjectType, Resolver, Store


class MainWindow(QMainWindow):
    """
    Main window for O3DE Pilot GUI.
    
    Features:
    - Object catalog (main view)
    - Menu bar with file/edit/view/help menus
    - Status bar
    - Settings persistence
    """
    
    WINDOW_TITLE = "O3DE Pilot"
    WINDOW_MIN_SIZE = QSize(1024, 768)
    ORGANIZATION = "O3DE"
    APPLICATION = "Pilot"
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_window()
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._load_settings()
    
    def _setup_window(self):
        """Set up the main window."""
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(self.WINDOW_MIN_SIZE)
        
        # Dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #222222;
            }
            QMenuBar {
                background-color: #1A1A1A;
                color: #EEEEEE;
                border-bottom: 1px solid #333333;
                padding: 4px;
            }
            QMenuBar::item {
                padding: 6px 12px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #333333;
            }
            QMenu {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
            }
            QMenu::item {
                padding: 8px 24px;
            }
            QMenu::item:selected {
                background-color: #00A0FC;
            }
            QMenu::separator {
                height: 1px;
                background-color: #444444;
                margin: 4px 12px;
            }
            QStatusBar {
                background-color: #1A1A1A;
                color: #888888;
                border-top: 1px solid #333333;
            }
        """)
    
    def _setup_menu_bar(self):
        """Set up the menu bar."""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("&File")
        
        open_action = QAction("&Open Manifest...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_manifest)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)
        
        force_refresh_action = QAction("Force Refresh (Clear Cache)", self)
        force_refresh_action.setShortcut("Ctrl+Shift+R")
        force_refresh_action.triggered.connect(self._on_force_refresh)
        file_menu.addAction(force_refresh_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menu_bar.addMenu("&View")
        
        # Type filter submenu
        type_menu = view_menu.addMenu("Filter by Type")
        
        all_types_action = QAction("All Types", self)
        all_types_action.triggered.connect(lambda: self._set_type_filter(None))
        type_menu.addAction(all_types_action)
        
        type_menu.addSeparator()
        
        for obj_type in ObjectType:
            action = QAction(obj_type.value.capitalize() + "s", self)
            action.triggered.connect(lambda checked, t=obj_type: self._set_type_filter(t))
            type_menu.addAction(action)
        
        view_menu.addSeparator()
        
        reset_filters_action = QAction("Reset Filters", self)
        reset_filters_action.triggered.connect(self._on_reset_filters)
        view_menu.addAction(reset_filters_action)
        
        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        
        about_action = QAction("&About O3DE Pilot", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _setup_central_widget(self):
        """Set up the central widget."""
        # Stacked widget for multiple screens (future expansion)
        self._stack = QStackedWidget()
        
        # Main catalog screen
        self._catalog = ObjectCatalogScreen()
        self._catalog.refreshRequested.connect(self._on_refresh)
        self._catalog.objectSelected.connect(self._on_object_selected)
        self._catalog.objectAdded.connect(self._on_object_added)
        self._catalog.objectRemoved.connect(self._on_object_removed)
        self._catalog.objectDownloaded.connect(self._on_object_download_requested)
        
        # Keep reference to store for downloads
        self._store = None
        
        self._stack.addWidget(self._catalog)
        self.setCentralWidget(self._stack)
    
    def _setup_status_bar(self):
        """Set up the status bar."""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")
    
    def _load_settings(self):
        """Load window settings."""
        settings = QSettings(self.ORGANIZATION, self.APPLICATION)
        
        # Restore geometry
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        # Restore state
        state = settings.value("window/state")
        if state:
            self.restoreState(state)
    
    def _save_settings(self):
        """Save window settings."""
        settings = QSettings(self.ORGANIZATION, self.APPLICATION)
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())
    
    def closeEvent(self, event: QCloseEvent):
        """Handle window close."""
        self._save_settings()
        event.accept()
    
    # Menu actions
    
    def _on_open_manifest(self):
        """Handle open manifest action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open O3DE Manifest",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.load_manifest(Path(file_path))
    
    def _on_refresh(self):
        """Handle refresh action."""
        self._status_bar.showMessage("Refreshing...")
        self.load_from_resolver()
        self._status_bar.showMessage("Refreshed", 3000)
    
    def _on_force_refresh(self):
        """Handle force refresh action (clears cache first)."""
        from ..core import Cache
        
        self._status_bar.showMessage("Clearing cache...")
        QApplication.processEvents()
        
        cache = Cache()
        cleared = cache.clear()
        self._status_bar.showMessage(f"Cleared {cleared} cached entries")
        QApplication.processEvents()
        
        self.load_from_resolver()
        self._status_bar.showMessage("Force refresh complete", 3000)
    
    def _set_type_filter(self, object_type: Optional[ObjectType]):
        """Set the type filter."""
        self._catalog.set_type_filter(object_type)
    
    def _on_reset_filters(self):
        """Reset all filters."""
        self._catalog.reset_filters()
    
    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About O3DE Pilot",
            "<h2>O3DE Pilot</h2>"
            "<p>Version 0.1.0</p>"
            "<p>AI-powered project management for Open 3D Engine.</p>"
            "<p>Licensed under Apache-2.0 OR MIT</p>"
        )
    
    # Signal handlers
    
    def _on_object_selected(self, info: ObjectInfo):
        """Handle object selection."""
        self._status_bar.showMessage(f"Selected: {info.display_name} ({info.object_type.value})")
    
    def _on_object_added(self, info: ObjectInfo):
        """Handle object added."""
        self._status_bar.showMessage(f"Added: {info.display_name}")
    
    def _on_object_removed(self, info: ObjectInfo):
        """Handle object removed."""
        self._status_bar.showMessage(f"Removed: {info.display_name}")
    
    def _on_object_download_requested(self, info: ObjectInfo):
        """Handle download request for a remote object."""
        from pathlib import Path
        import shutil
        from ..core import get_default_gems_path
        
        if not self._store:
            self._status_bar.showMessage("No remote store available", 5000)
            return
        
        # Get selected version from inspector dropdown
        selected_version = self._catalog.get_selected_version()
        
        # Find the RemoteObject in the store (use selected version if available)
        if selected_version:
            remote_obj = self._store.get_version(
                info.object_type.value, info.name, selected_version
            )
            version_to_download = selected_version
        else:
            key = f"{info.object_type.value}:{info.name}"
            remote_obj = self._store.objects.get(key)
            version_to_download = info.version
        
        if not remote_obj:
            self._status_bar.showMessage(f"Object not found in store: {info.name}", 5000)
            return
        
        # Determine download path based on type
        if info.object_type.value == "gem":
            target_path = get_default_gems_path()
        else:
            from ..core import get_o3de_path
            target_path = get_o3de_path() / f"{info.object_type.value}s"
        
        # Compute the destination folder: <name>/<version>/
        folder_name = info.name.replace(".", "_")
        dest_path = target_path / folder_name / version_to_download
        
        # Check if already exists
        if dest_path.exists():
            reply = QMessageBox.question(
                self,
                "Already Downloaded",
                f"'{info.display_name}' v{version_to_download} already exists at:\n{dest_path}\n\nDo you want to re-download (delete existing)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self._status_bar.showMessage("Download cancelled", 3000)
                return
            # Remove existing
            try:
                shutil.rmtree(dest_path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not remove existing folder:\n{e}")
                return
        
        self._status_bar.showMessage(f"Downloading {info.display_name} v{version_to_download}...")
        QApplication.processEvents()
        
        try:
            downloaded_path = self._store.download_sync(
                remote_obj, 
                target_path,
                progress_callback=lambda msg, cur, total: (
                    self._status_bar.showMessage(msg),
                    QApplication.processEvents()
                )
            )
            
            self._status_bar.showMessage(f"Downloaded to {downloaded_path}", 10000)
            
            # Show success dialog
            QMessageBox.information(
                self,
                "Download Complete",
                f"Successfully downloaded '{info.display_name}' v{version_to_download} to:\n{downloaded_path}"
            )
            
            # Refresh the catalog to show the newly downloaded local item
            self.load_from_resolver()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Download Failed",
                f"Failed to download {info.display_name}:\n{e}"
            )
            self._status_bar.showMessage("Download failed", 5000)
    
    # Public methods
    
    def load_manifest(self, manifest_path: Path):
        """Load objects from a manifest file."""
        try:
            from ..core import Manifest
            import json
            
            with open(manifest_path) as f:
                data = json.load(f)
            
            manifest = Manifest.model_validate(data)
            self._load_from_manifest(manifest)
            self._status_bar.showMessage(f"Loaded: {manifest_path.name}", 5000)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading Manifest",
                f"Failed to load manifest:\n{e}"
            )
    
    def _load_from_manifest(self, manifest):
        """Load objects from a Manifest object."""
        self._catalog.clear()
        
        # Load all object types from manifest
        for attr, obj_type in [
            ('engines', ObjectType.ENGINE),
            ('projects', ObjectType.PROJECT),
            ('gems', ObjectType.GEM),
            ('templates', ObjectType.TEMPLATE),
            ('repos', ObjectType.REPO),
            ('overlays', ObjectType.OVERLAY),
        ]:
            objects = getattr(manifest, attr, None) or []
            for obj in objects:
                info = ObjectInfo.from_o3de_object(obj)
                self._catalog.add_object(info)
    
    def load_from_resolver(self):
        """Load objects from the current resolver and remote repos."""
        try:
            from ..core import resolve_manifest, get_manifest_path, Store
            import json
            
            manifest_path = get_manifest_path()
            if not manifest_path.exists():
                self._status_bar.showMessage("No manifest found", 5000)
                return
            
            self._catalog.clear()
            local_count = 0
            remote_count = 0
            
            # Load local objects from resolver
            resolver = resolve_manifest(manifest_path)
            for resolved_obj in resolver.objects.values():
                info = ObjectInfo.from_resolved_object(resolved_obj)
                self._catalog.add_object(info)
                local_count += 1
            
            # Load remote objects from Store
            try:
                with open(manifest_path) as f:
                    manifest_data = json.load(f)
                
                remote = manifest_data.get("remote", {})
                repo_urls = remote.get("repos", [])
                
                if repo_urls:
                    self._status_bar.showMessage("Fetching remote repos...")
                    QApplication.processEvents()
                    
                    self._store = Store()
                    remote_count = self._store.refresh_sync(repo_urls)
                    
                    for remote_obj in self._store.objects.values():
                        # Skip repos - they're just containers
                        if remote_obj.object_type.value == "repo":
                            continue
                        info = ObjectInfo.from_remote_object(remote_obj)
                        # Add available versions from store
                        info.available_versions = self._store.get_versions(
                            remote_obj.object_type, remote_obj.name
                        )
                        self._catalog.add_object(info)
                        
            except Exception as e:
                import traceback
                traceback.print_exc()
                # Continue with local objects even if remote fails
                self._status_bar.showMessage(f"Remote fetch failed: {e}", 5000)
            
            self._status_bar.showMessage(
                f"Loaded {local_count} local + {remote_count} remote objects",
                5000
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._status_bar.showMessage(f"Error: {e}", 5000)
    
    def load_demo_objects(self):
        """Load demo objects for testing."""
        demo_objects = [
            ObjectInfo(
                name="o3de",
                display_name="Open 3D Engine",
                object_type=ObjectType.ENGINE,
                version="24.09.0",
                origin=ObjectOrigin.LOCAL,
                summary="The O3DE open source game engine.",
                creator="O3DE Foundation",
            ),
            ObjectInfo(
                name="atom",
                display_name="Atom Renderer",
                object_type=ObjectType.GEM,
                version="1.0.0",
                origin=ObjectOrigin.LOCAL,
                summary="Multi-platform, physically-based renderer.",
                creator="O3DE Foundation",
                is_added=True,
            ),
            ObjectInfo(
                name="script-canvas",
                display_name="Script Canvas",
                object_type=ObjectType.GEM,
                version="1.0.0",
                origin=ObjectOrigin.LOCAL,
                summary="Visual scripting system for O3DE.",
                creator="O3DE Foundation",
                is_added=True,
            ),
            ObjectInfo(
                name="physx",
                display_name="PhysX",
                object_type=ObjectType.GEM,
                version="5.1.0",
                origin=ObjectOrigin.LOCAL,
                summary="NVIDIA PhysX integration for O3DE.",
                creator="O3DE Foundation",
            ),
            ObjectInfo(
                name="aws-core",
                display_name="AWS Core",
                object_type=ObjectType.GEM,
                version="1.0.0",
                origin=ObjectOrigin.REMOTE,
                summary="Core AWS integration for O3DE.",
                creator="Amazon",
            ),
            ObjectInfo(
                name="multiplayer",
                display_name="Multiplayer",
                object_type=ObjectType.GEM,
                version="1.0.0",
                origin=ObjectOrigin.LOCAL,
                summary="Multiplayer networking for O3DE.",
                creator="O3DE Foundation",
            ),
            ObjectInfo(
                name="default-project",
                display_name="Default Project",
                object_type=ObjectType.PROJECT,
                version="1.0.0",
                origin=ObjectOrigin.LOCAL,
                summary="A default O3DE project template.",
                creator="O3DE Foundation",
            ),
            ObjectInfo(
                name="minimal-project",
                display_name="Minimal Project",
                object_type=ObjectType.TEMPLATE,
                version="1.0.0",
                origin=ObjectOrigin.LOCAL,
                summary="Minimal project template with essential features.",
                creator="O3DE Foundation",
            ),
            ObjectInfo(
                name="o3de-extras",
                display_name="O3DE Extras",
                object_type=ObjectType.REPO,
                version="1.0.0",
                origin=ObjectOrigin.REMOTE,
                summary="Additional gems and templates for O3DE.",
                creator="O3DE Foundation",
            ),
        ]
        
        self._catalog.add_objects(demo_objects)
        self._status_bar.showMessage(f"Loaded {len(demo_objects)} demo objects", 5000)
