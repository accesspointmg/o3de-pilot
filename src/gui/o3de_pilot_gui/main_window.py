# O3DE Pilot GUI - Main Window
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Main application window for O3DE Pilot GUI.
"""

from typing import Optional
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QSize, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QAction, QIcon, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QTabWidget,
    QMenuBar, QMenu, QToolBar, QStatusBar, QMessageBox,
    QFileDialog, QApplication, QLabel
)

from .object_catalog_screen import ObjectCatalogScreen
from .object_tree_screen import ObjectTreeScreen
from .ai_panel import AIPanel
from .terminal_panel import TerminalPanel
from .workspace_tab import WorkspaceTab
from .object_info import ObjectInfo, ObjectOrigin, DownloadStatus
from .object_model import ObjectModel, ObjectRole
from .settings_dialog import SettingsDialog
from o3de_cli.core import ObjectType, Resolver, Store, get_manifest_path
from o3de_cli.core.network import NetworkStatus, is_online


class DownloadWorker(QObject):
    """Worker for downloading objects in a background thread."""
    
    progress = Signal(str, int, int)  # name, current, total (0-100)
    finished = Signal(str, object)    # name, downloaded_path (Path or None on error)
    error = Signal(str, str)          # name, error message
    
    def __init__(self, remote_obj, target_path: Path, name: str):
        super().__init__()
        self._remote_obj = remote_obj
        self._target_path = target_path
        self._name = name
    
    def run(self):
        """Execute the download."""
        try:
            # Create a fresh store in the worker thread for thread safety
            store = Store()
            
            def progress_callback(msg: str, current: int, total: int):
                # current is already 0-100 percentage
                self.progress.emit(self._name, current, total)
            
            downloaded_path = store.download_sync(
                self._remote_obj,
                self._target_path,
                progress_callback=progress_callback,
                use_version_folders=False
            )
            
            self.finished.emit(self._name, downloaded_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(self._name, str(e))


class BranchResolverWorker(QObject):
    """Worker for resolving git branches and checking clone status in a background thread."""
    
    # Emitted when a branch is resolved for an object
    # (object_type, name, branch, is_cloned_locally)
    branch_resolved = Signal(str, str, str, bool)
    # Emitted when all branches are resolved
    finished = Signal()
    
    def __init__(self, objects: list, local_objects: list):
        """
        Args:
            objects: List of tuples (object_type, name, repository_url) to resolve
            local_objects: List of tuples (path,) for local objects to collect git remotes
        """
        super().__init__()
        self._objects = objects
        self._local_objects = local_objects
        self._should_stop = False
    
    def stop(self):
        """Request the worker to stop."""
        self._should_stop = True
    
    def run(self):
        """Execute branch resolution for all objects."""
        from o3de_cli.core.git_utils import (
            get_default_branch, is_git_url, is_url_cloned_locally,
            normalize_git_url, get_local_git_remote,
        )
        
        # Build local_repo_urls set in the background thread
        local_repo_urls: set[str] = set()
        for (path,) in self._local_objects:
            if self._should_stop:
                break
            remote_url = get_local_git_remote(path)
            if remote_url:
                local_repo_urls.add(normalize_git_url(remote_url))
        
        for obj_type, name, repo_url in self._objects:
            if self._should_stop:
                break
            
            if not repo_url or not is_git_url(repo_url):
                continue
            
            # Check if cloned locally
            is_cloned = is_url_cloned_locally(repo_url, local_repo_urls)
            
            branch = get_default_branch(repo_url, timeout=5.0)
            if branch:
                self.branch_resolved.emit(obj_type, name, branch, is_cloned)
            else:
                # Even without branch, we can report clone status
                self.branch_resolved.emit(obj_type, name, "", is_cloned)
        
        self.finished.emit()


class HashCheckerWorker(QObject):
    """Worker for periodically checking if source files have changed."""
    
    # Emitted when file changes are detected
    changes_detected = Signal(list)  # list of changed files
    # Emitted on each check cycle (for debugging)
    check_completed = Signal(bool)  # True if changes found
    
    def __init__(self, check_interval_seconds: int = 30):
        super().__init__()
        self._check_interval = check_interval_seconds
        self._should_stop = False
    
    def stop(self):
        """Request the worker to stop."""
        self._should_stop = True
    
    def run(self):
        """Execute periodic hash checking."""
        import time
        from o3de_cli.core.resolver import check_files_changed
        
        while not self._should_stop:
            # Check for changes
            has_changes, changed_files = check_files_changed()
            
            if has_changes:
                self.changes_detected.emit(changed_files)
            
            self.check_completed.emit(has_changes)
            
            # Sleep in small increments to allow stopping
            for _ in range(self._check_interval * 10):
                if self._should_stop:
                    break
                time.sleep(0.1)


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
    
    def __init__(self, parent: Optional[QWidget] = None, *, offline: bool = False):
        super().__init__(parent)
        self._offline = offline

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
        
        self._force_refresh_action = QAction("Force Refresh (Clear Cache)", self)
        self._force_refresh_action.setShortcut("Ctrl+Shift+R")
        self._force_refresh_action.triggered.connect(self._on_force_refresh)
        file_menu.addAction(self._force_refresh_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menu_bar.addMenu("&Edit")
        
        preferences_action = QAction("&Preferences...", self)
        preferences_action.setShortcut("Ctrl+,")
        preferences_action.triggered.connect(self._on_preferences)
        edit_menu.addAction(preferences_action)
        
        ai_settings_action = QAction("AI &Settings...", self)
        ai_settings_action.triggered.connect(self._on_ai_settings)
        edit_menu.addAction(ai_settings_action)
        
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

        view_menu.addSeparator()

        # AI Panel toggle — added after _setup_central_widget creates the panel
        self._view_menu = view_menu
        
        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        
        about_action = QAction("&About O3DE Pilot", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _setup_central_widget(self):
        """Set up the central widget."""
        # Tab widget: Catalog + Object Tree
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background-color: #2D2D2D;
                color: #AAAAAA;
                border: none;
                padding: 8px 20px;
                margin-right: 1px;
            }
            QTabBar::tab:selected {
                background-color: #222222;
                color: #EEEEEE;
                border-bottom: 2px solid #0078D4;
            }
            QTabBar::tab:hover {
                background-color: #3D3D3D;
                color: #EEEEEE;
            }
        """)
        
        # Main catalog screen
        self._catalog = ObjectCatalogScreen()
        self._catalog.refreshRequested.connect(self._on_refresh)
        self._catalog.objectSelected.connect(self._on_object_selected)
        self._catalog.objectDownloaded.connect(self._on_object_download_requested)
        self._catalog.commandRequested.connect(self._run_command_dialog)
        self._catalog.unregisterRequested.connect(self._on_direct_unregister)
        
        # Object tree screen
        self._tree_screen = ObjectTreeScreen()
        self._tree_screen.commandRequested.connect(self._run_command_dialog)
        
        self._tabs.addTab(self._catalog, "Catalog")
        self._tabs.addTab(self._tree_screen, "Object Tree")
        
        # Workspace browser tab
        self._workspace_tab = WorkspaceTab()
        self._workspace_tab.commandRequested.connect(self._run_command_dialog)
        self._tabs.addTab(self._workspace_tab, "Workspaces")
        
        # Keep reference to store for downloads
        self._store = None
        
        # Track active downloads: name -> (thread, worker, info)
        self._downloads: dict[str, tuple[QThread, DownloadWorker, ObjectInfo]] = {}
        
        # Track branch resolver thread
        self._branch_resolver_thread: Optional[QThread] = None
        self._branch_resolver_worker: Optional[BranchResolverWorker] = None
        
        # Track hash checker thread for detecting file changes
        self._hash_checker_thread: Optional[QThread] = None
        self._hash_checker_worker: Optional[HashCheckerWorker] = None
        
        self.setCentralWidget(self._tabs)

        # AI panel (dockable, always visible)
        self._ai_panel = AIPanel(self)
        self._ai_panel.execute_command.connect(self._on_ai_execute_command)
        self.addDockWidget(Qt.RightDockWidgetArea, self._ai_panel)

        # Terminal panel (dockable, bottom)
        self._terminal_panel = TerminalPanel(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._terminal_panel)

        # Add AI Panel toggle to View menu
        self._view_menu.addAction(self._ai_panel.toggleViewAction())
        self._view_menu.addAction(self._terminal_panel.toggleViewAction())
    
    def _setup_status_bar(self):
        """Set up the status bar."""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        
        # Network status indicator (permanent widget on right side)
        # Using a clickable label for debug/testing purposes
        self._network_indicator = QLabel()
        self._network_indicator.setStyleSheet("""
            QLabel {
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 8pt;
                font-weight: bold;
            }
        """)
        self._network_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self._network_indicator.mousePressEvent = self._on_network_indicator_clicked
        self._network_click_count = 0
        self._status_bar.addPermanentWidget(self._network_indicator)
        
        # Initial network check and indicator update
        self._is_online = not self._offline  # Assume offline if flag set
        self._simulating_offline = self._offline
        self._update_network_indicator()
        
        # Set up network status listener (uses Qt signal for thread safety)
        self._network_check_timer = QTimer(self)
        self._network_check_timer.timeout.connect(self._check_network_status)
        if not self._offline:
            self._network_check_timer.start(30000)  # Check every 30 seconds
        
        # Do initial network check
        if not self._offline:
            QTimer.singleShot(100, self._check_network_status)
        
        self._status_bar.showMessage("Ready")
    
    def _check_network_status(self):
        """Check network status and update UI accordingly."""
        # Don't override simulated offline mode
        if self._simulating_offline:
            return
        
        was_online = self._is_online
        self._is_online = is_online(force_check=True)
        
        if was_online != self._is_online:
            self._update_network_indicator()
            self._update_network_dependent_ui()
    
    def _update_network_indicator(self):
        """Update the network status indicator in status bar."""
        if self._is_online:
            self._network_indicator.setText("● Online")
            self._network_indicator.setStyleSheet("""
                QLabel {
                    padding: 2px 8px;
                    border-radius: 3px;
                    font-size: 8pt;
                    font-weight: bold;
                    color: #00CC66;
                    background-color: #1A3320;
                }
            """)
            self._network_indicator.setToolTip("Click 5 times to simulate offline mode")
        elif self._simulating_offline:
            self._network_indicator.setText("● Offline (Simulated)")
            self._network_indicator.setStyleSheet("""
                QLabel {
                    padding: 2px 8px;
                    border-radius: 3px;
                    font-size: 8pt;
                    font-weight: bold;
                    color: #FFAA00;
                    background-color: #332B1A;
                }
            """)
            self._network_indicator.setToolTip("Click 5 times to restore network detection")
        else:
            self._network_indicator.setText("● Offline")
            self._network_indicator.setStyleSheet("""
                QLabel {
                    padding: 2px 8px;
                    border-radius: 3px;
                    font-size: 8pt;
                    font-weight: bold;
                    color: #FF6666;
                    background-color: #331A1A;
                }
            """)
            self._network_indicator.setToolTip("No internet connection detected")
    
    def _update_network_dependent_ui(self):
        """Enable/disable UI elements that require network access."""
        # Update menu actions
        self._force_refresh_action.setEnabled(self._is_online)
        
        # Update catalog refresh and download buttons
        self._catalog.set_refresh_enabled(self._is_online)
        self._catalog.set_download_enabled(self._is_online)
        
        # Show status message
        if not self._is_online:
            self._status_bar.showMessage("Offline mode - using cached data", 5000)
    
    def _on_network_indicator_clicked(self, event):
        """Handle clicks on the network indicator for debug purposes."""
        self._network_click_count += 1
        
        if self._network_click_count >= 5:
            self._network_click_count = 0
            
            if self._simulating_offline:
                # Currently simulating offline - offer to restore
                reply = QMessageBox.question(
                    self,
                    "Network Simulation",
                    "Currently simulating offline mode.\n\n"
                    "Do you want to restore normal network detection?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._simulating_offline = False
                    NetworkStatus.set_offline_for_testing(offline=False)
                    # Force a real check
                    NetworkStatus._last_check = 0
                    self._check_network_status()
                    self._status_bar.showMessage("Restored normal network detection", 3000)
            else:
                # Offer to simulate offline
                reply = QMessageBox.question(
                    self,
                    "Network Simulation",
                    "Do you want to simulate offline mode?\n\n"
                    "This is useful for testing offline functionality.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._simulating_offline = True
                    self._is_online = False
                    NetworkStatus.set_offline_for_testing(offline=True)
                    self._update_network_indicator()
                    self._update_network_dependent_ui()
                    self._status_bar.showMessage("Simulating offline mode", 3000)
    
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
        
        # Restore simulated offline state
        simulating_offline = settings.value("network/simulating_offline", False, type=bool)
        if simulating_offline:
            self._simulating_offline = True
            self._is_online = False
            NetworkStatus.set_offline_for_testing(offline=True)
            self._update_network_indicator()
            self._update_network_dependent_ui()
    
    def _save_settings(self):
        """Save window settings."""
        settings = QSettings(self.ORGANIZATION, self.APPLICATION)
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())
        settings.setValue("network/simulating_offline", self._simulating_offline)
    
    def closeEvent(self, event: QCloseEvent):
        """Handle window close."""
        # Stop background workers
        self._workspace_tab._cleanup_threads()
        self._stop_hash_checker()
        self._stop_branch_resolver()
        
        # Stop network check timer
        if hasattr(self, '_network_check_timer'):
            self._network_check_timer.stop()

        self._ai_panel.save_sessions()
        self._terminal_panel.stop()
        self._save_settings()
        event.accept()

    def _stop_branch_resolver(self):
        """Stop the branch resolver background thread."""
        try:
            if self._branch_resolver_thread and self._branch_resolver_thread.isRunning():
                if self._branch_resolver_worker:
                    self._branch_resolver_worker.stop()
                self._branch_resolver_thread.quit()
                self._branch_resolver_thread.wait(2000)
        except RuntimeError:
            pass
    
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
        self._reload_async()
    
    def _on_force_refresh(self):
        """Handle force refresh action (clears cache first)."""
        # Check if online
        if not self._is_online:
            QMessageBox.warning(
                self,
                "Offline Mode",
                "Force refresh is not available while offline.\n\n"
                "The application will continue using cached data."
            )
            return
        
        from o3de_cli.core import Cache
        
        self._status_bar.showMessage("Clearing cache...")
        QApplication.processEvents()
        
        cache = Cache()
        cleared = cache.clear()
        self._status_bar.showMessage(f"Cleared {cleared} cached entries")
        QApplication.processEvents()
        
        self._reload_async()
    
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
    
    def _on_ai_settings(self):
        """Show AI settings dialog."""
        from .ai_settings_dialog import AISettingsDialog
        dialog = AISettingsDialog(self)
        dialog.exec()
        # Refresh animation state in case provider was changed
        self._ai_panel.refresh_ai_state()

    def _on_solve_workspace(self):
        """Show the workspace solver dialog."""
        from .workspace_solver_dialog import WorkspaceSolverDialog
        from o3de_cli.core import get_manifest_path, Resolver

        manifest_path = get_manifest_path()
        if not manifest_path.exists():
            QMessageBox.warning(self, "No Manifest", "No manifest found.")
            return

        try:
            resolver = Resolver(manifest_path)
            resolver.resolve()
        except Exception as e:
            QMessageBox.critical(
                self, "Resolve Error", f"Failed to resolve manifest:\n{e}"
            )
            return

        store = getattr(self, "_store", None)
        dialog = WorkspaceSolverDialog(
            resolver=resolver, store=store, parent=self,
        )
        dialog.exec()
        # Refresh workspace tab in case a new workspace was created
        self._workspace_tab.refresh()

    # ── CLI command execution ──────────────────────────────────────

    def _run_command_dialog(self, spec: dict, *, selected_object=None):
        """Show a CommandDialog for *spec*, run it, and show the output."""
        from .command_dialog import show_command_dialog

        result = show_command_dialog(
            spec, parent=self, selected_object=selected_object,
        )
        if result is None:
            return  # cancelled

        _, tokens, values = result
        will_register = bool(values.get("auto_register"))

        cmd_str = "o3de " + " ".join(tokens)
        if will_register:
            name = values.get("name", "")
            path = values.get("path", "")
            if not path and name:
                from o3de_cli.core.paths import get_default_path_for_type
                from o3de_cli.core.models import ObjectType
                obj_types = spec.get("object_types", [])
                if obj_types:
                    try:
                        otype = ObjectType(obj_types[0].lower())
                        path = str(get_default_path_for_type(otype) / name)
                    except Exception:
                        pass
            if path:
                cmd_str += f" && o3de register {path}"

        self._terminal_panel.execute_command(cmd_str)
        self._terminal_panel.show()

        # Refresh after state-changing commands (poll a few times to catch slow ops)
        if spec.get("state_changing"):
            from PySide6.QtCore import QTimer
            for delay in (500, 2000, 5000):
                QTimer.singleShot(delay, self._on_refresh)

    def _on_direct_unregister(self, info):
        """Unregister an object directly without showing a dialog."""
        if not info or not getattr(info, "path", None):
            return
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Unregister",
            f"Unregister {info.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._terminal_panel.execute_command(f"o3de unregister {info.path}")
        self._terminal_panel.show()
        self._on_refresh()

    def _on_ai_execute_command(self, command: str, args: dict):
        """Execute an o3de-pilot command triggered by the AI panel."""
        tokens = command.split()
        for k, v in args.items():
            if v:
                tokens.append(str(v))

        cmd_str = " ".join(tokens)
        self._terminal_panel.execute_command(f"o3de {cmd_str}")
        self._terminal_panel.show()

    def _on_preferences(self):
        """Show preferences dialog."""
        import json
        import subprocess
        import sys
        
        manifest_path = get_manifest_path()
        
        # Load current manifest
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load manifest:\n{e}"
            )
            return
        
        # Show dialog
        dialog = SettingsDialog(self)
        dialog.load_from_manifest(manifest_data)
        
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            # Get updated values from dialog
            updated = dialog.save_to_manifest(manifest_data)
            
            # Use CLI commands to persist changes
            errors = []
            
            # Set country
            country_code = updated.get("country", {}).get("code")
            if country_code:
                result = subprocess.run(
                    [sys.executable, "-m", "o3de_cli", "manifest", "set", "country.code", country_code],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    err = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                    errors.append(f"country.code: {err}")
            
            # Set default paths
            defaults = updated.get("default", {})
            for key, value in defaults.items():
                if value:
                    result = subprocess.run(
                        [sys.executable, "-m", "o3de_cli", "manifest", "set", f"default.{key}", value],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode != 0:
                        err = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                        errors.append(f"default.{key}: {err}")
            
            if errors:
                QMessageBox.warning(
                    self,
                    "Partial Save",
                    f"Some settings could not be saved:\n" + "\n".join(errors)
                )
            else:
                self._status_bar.showMessage("Preferences saved", 5000)
    
    # Signal handlers
    
    def _on_object_selected(self, info: ObjectInfo):
        """Handle object selection."""
        self._status_bar.showMessage(f"Selected: {info.display_name} ({info.object_type.value})")
    
    def _find_object_json(self, downloaded_path: Path, obj_type: str) -> Optional[Path]:
        """Find the object's json file in downloaded folder."""
        # Look for type-specific json file first
        type_json = downloaded_path / f"{obj_type}.json"
        if type_json.exists():
            return type_json
        
        # Search recursively for <type>.json
        for json_file in downloaded_path.rglob(f"{obj_type}.json"):
            return json_file
        
        # Fallback: any json file in root
        for json_file in downloaded_path.glob("*.json"):
            return json_file
        
        return None
    
    def _register_downloaded_object(self, json_path: Path, obj_type: str):
        """Register a downloaded object's json file in the manifest."""
        import json
        from o3de_cli.core import get_manifest_path
        from o3de_cli.commands.register import register_object_path
        
        manifest_path = get_manifest_path()
        if not manifest_path.exists():
            return
        
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
            
            # Register the path
            registered = register_object_path(manifest_data, json_path, obj_type)
            
            if registered:
                # Write back the manifest
                with open(manifest_path, "w") as f:
                    json.dump(manifest_data, f, indent=4)
        except Exception as e:
            print(f"Warning: Could not register {json_path}: {e}")
    
    def _on_object_download_requested(self, info: ObjectInfo):
        """Handle download request for a remote object."""
        import shutil
        
        if not self._store:
            self._status_bar.showMessage("No remote store available", 5000)
            return
        
        # Check if already downloading this object
        download_key = f"{info.object_type.value}:{info.name}"
        if download_key in self._downloads:
            self._status_bar.showMessage(f"Already downloading {info.display_name}", 3000)
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
        
        # Determine download path: <o3de_path>/<type>s/<name>/<version>/src/
        from o3de_cli.core import get_o3de_path
        obj_type_plural = f"{info.object_type.value}s"
        target_path = get_o3de_path() / obj_type_plural / info.name / version_to_download / "src"
        
        # Check if already exists
        if target_path.exists():
            reply = QMessageBox.question(
                self,
                "Already Downloaded",
                f"'{info.display_name}' v{version_to_download} already exists at:\n{target_path}\n\nDo you want to re-download (delete existing)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self._status_bar.showMessage("Download cancelled", 3000)
                return
            # Remove existing
            try:
                shutil.rmtree(target_path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not remove existing folder:\n{e}")
                return
        
        # Update model to show downloading state
        model = self._catalog.model
        index = model.find_by_name(info.object_type, info.name, info.version)
        if index and index.isValid():
            ObjectModel.set_download_status(model, index, DownloadStatus.DOWNLOADING)
            ObjectModel.set_download_progress(model, index, 0)
        
        self._status_bar.showMessage(f"Downloading {info.display_name}...")
        
        # Create worker and thread
        thread = QThread()
        worker = DownloadWorker(remote_obj, target_path, download_key)
        worker.moveToThread(thread)
        
        # Connect signals
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(self._on_download_finished)
        worker.error.connect(self._on_download_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_download(download_key))
        
        # Store reference and start
        self._downloads[download_key] = (thread, worker, info)
        thread.start()
    
    def _on_download_progress(self, name: str, current: int, total: int):
        """Handle download progress update."""
        if name not in self._downloads:
            return
        
        _, _, info = self._downloads[name]
        
        # Update model progress
        model = self._catalog.model
        index = model.find_by_name(info.object_type, info.name, info.version)
        if index and index.isValid():
            ObjectModel.set_download_progress(model, index, current)
        
        self._status_bar.showMessage(f"Downloading {info.display_name}: {current}%")
    
    def _on_download_finished(self, name: str, downloaded_path):
        """Handle download completion."""
        if name not in self._downloads:
            return
        
        _, _, info = self._downloads[name]
        
        # Find the actual json file in downloaded folder and register it
        if downloaded_path:
            json_file = self._find_object_json(downloaded_path, info.object_type.value)
            if json_file:
                self._register_downloaded_object(json_file, info.object_type.value)
        
        # Update model
        model = self._catalog.model
        index = model.find_by_name(info.object_type, info.name, info.version)
        if index and index.isValid():
            ObjectModel.set_download_status(model, index, DownloadStatus.DOWNLOADED)
            ObjectModel.set_download_progress(model, index, 100)
        
        self._status_bar.showMessage(f"Downloaded {info.display_name}", 5000)
        
        # Refresh to show as local
        self.load_from_resolver()
    
    def _on_download_error(self, name: str, error_msg: str):
        """Handle download error."""
        if name not in self._downloads:
            return
        
        _, _, info = self._downloads[name]
        
        # Update model
        model = self._catalog.model
        index = model.find_by_name(info.object_type, info.name, info.version)
        if index and index.isValid():
            ObjectModel.set_download_status(model, index, DownloadStatus.DOWNLOAD_FAILED)
            ObjectModel.set_download_progress(model, index, 0)
        
        QMessageBox.critical(
            self,
            "Download Failed",
            f"Failed to download {info.display_name}:\n{error_msg}"
        )
        self._status_bar.showMessage("Download failed", 5000)
    
    def _cleanup_download(self, name: str):
        """Clean up download tracking after completion."""
        if name in self._downloads:
            del self._downloads[name]
    
    # Public methods
    
    def load_manifest(self, manifest_path: Path):
        """Load objects from a manifest file."""
        try:
            from o3de_cli.core import Manifest
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
    
    def load_from_resolver(self, status_callback=None):
        """Load objects from the current resolver and remote repos.

        Args:
            status_callback: Optional callable(status_text, detail_text) for
                progress reporting (used by the splash screen).

        .. note:: Prefer :meth:`_reload_async` for GUI-triggered reloads.
            This synchronous method is kept for the initial manifest-path
            load and programmatic use.
        """
        # Re-entrancy guard — if a reload is already in progress, skip.
        if getattr(self, "_is_loading", False):
            return
        def _status(msg, detail=""):
            if status_callback:
                status_callback(msg, detail)
            QApplication.processEvents()

        try:
            from o3de_cli.core import get_manifest_path, Store
            from o3de_cli.core.resolver import load_resolved_manifest
            import json

            _status("Locating manifest...")
            manifest_path = get_manifest_path()
            if not manifest_path.exists():
                self._status_bar.showMessage("No manifest found", 5000)
                return
            
            self._catalog.clear()
            local_count = 0
            remote_count = 0
            
            # Load local objects from cached resolved manifest (fast path)
            # Only re-resolves if source files have changed.
            # Remote objects in the resolver are minimal stubs (URL + type only,
            # no display_metadata) kept for tree navigation — skip them here.
            # The Store provides full details for remote objects below.
            _status("Resolving local objects...")
            local_keys = set()  # Track local object keys to skip duplicates
            resolved_data = load_resolved_manifest()
            
            objects_dict = resolved_data.get("objects", {})
            total_local = sum(1 for v in objects_dict.values() if v.get("status") != "remote")
            for name, obj_data in objects_dict.items():
                if obj_data.get("status") == "remote":
                    continue  # Skip remote stubs; Store provides full data
                info = ObjectInfo.from_resolved_dict(name, obj_data)
                self._catalog.add_object(info)
                # Track this object by type:name to skip it in remotes
                local_keys.add(f"{info.object_type.value}:{info.name}")
                local_count += 1
                if local_count % 20 == 0:
                    _status("Loading local objects...", f"{local_count} / {total_local}")
            
            # Load remote objects from Store
            try:
                with open(manifest_path) as f:
                    manifest_data = json.load(f)
                
                # Try "repos" at top level (o3de_manifest format) or under "remote" (2.0 format)
                repo_urls = manifest_data.get("repos", [])
                if not repo_urls:
                    remote = manifest_data.get("remote", {})
                    repo_urls = remote.get("repos", [])
                
                if repo_urls:
                    _status("Fetching remote repos...", f"{len(repo_urls)} repo(s)")
                    self._status_bar.showMessage("Fetching remote repos...")
                    QApplication.processEvents()
                    
                    self._store = Store()
                    remote_count = self._store.refresh_sync(repo_urls)
                    QApplication.processEvents()
                    
                    remote_processed = 0
                    for remote_obj in self._store.objects.values():
                        # Skip repos - they're just containers
                        if remote_obj.object_type.value == "repo":
                            continue
                        # Skip objects that are already local
                        remote_key = f"{remote_obj.object_type.value}:{remote_obj.name}"
                        if remote_key in local_keys:
                            continue
                        info = ObjectInfo.from_remote_object(remote_obj)
                        # Add available versions from store
                        info.available_versions = self._store.get_versions(
                            remote_obj.object_type, remote_obj.name
                        )
                        self._catalog.add_object(info)
                        remote_processed += 1
                        if remote_processed % 10 == 0:
                            QApplication.processEvents()
                    
                    # Update available_versions for local objects from store
                    from .object_info import ObjectOrigin
                    model = self._catalog.model
                    for row in range(model.rowCount()):
                        index = model.index(row, 0)
                        info = model.get_object_info(index)
                        if info and info.origin == ObjectOrigin.LOCAL and self._store:
                            versions = self._store.get_versions(
                                info.object_type, info.name
                            )
                            if versions:
                                info.available_versions = versions
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                # Continue with local objects even if remote fails
                self._status_bar.showMessage(f"Remote fetch failed: {e}", 5000)
            
            _status("Fetching GitHub releases...")
            # Fetch GitHub releases for local objects with git URLs that don't have versions
            from o3de_cli.core.git_utils import get_github_releases, get_local_git_upstream
            from .object_info import ObjectOrigin, ObjectType
            model = self._catalog.model
            github_checked = 0
            
            # First pass: collect engines and their releases by path
            engine_releases_by_path: dict[str, list[str]] = {}
            for row in range(model.rowCount()):
                index = model.index(row, 0)
                info = model.get_object_info(index)
                if info and info.origin == ObjectOrigin.LOCAL and info.object_type == ObjectType.ENGINE:
                    if info.path and info.json_releases:
                        engine_path = str(info.path).replace("\\", "/").rstrip("/")
                        engine_releases_by_path[engine_path] = info.json_releases
            
            # Second pass: process all objects, inheriting engine releases for children
            for row in range(model.rowCount()):
                index = model.index(row, 0)
                info = model.get_object_info(index)
                if info and info.origin == ObjectOrigin.LOCAL:
                    git_url = None
                    # Try upstream remote first (for forks), then origin
                    if info.path:
                        upstream = get_local_git_upstream(str(info.path))
                        if upstream and "github.com" in upstream:
                            git_url = upstream
                    # Fall back to stored repository_url
                    if not git_url:
                        git_url = info.repository_url or info.origin_url
                    if git_url and "github.com" in git_url:
                        github_releases = get_github_releases(git_url)
                        github_checked += 1
                        if github_checked % 5 == 0:
                            QApplication.processEvents()
                        if github_releases:
                            # Get JSON versions - either from object itself or inherited from parent engine
                            json_versions = set(info.json_releases)
                            
                            # If no releases and this is a child object, inherit from parent engine
                            if not json_versions and info.path and info.object_type != ObjectType.ENGINE:
                                obj_path = str(info.path).replace("\\", "/")
                                for engine_path, engine_releases in engine_releases_by_path.items():
                                    if obj_path.startswith(engine_path + "/"):
                                        json_versions = set(engine_releases)
                                        info.json_releases = engine_releases.copy()
                                        break
                            
                            # Find GitHub-only versions (not in JSON)
                            github_only = [v for v in github_releases if v not in json_versions]
                            info.github_only_versions = github_only
                            # Merge all versions (GitHub releases first, they're sorted newest-first)
                            all_versions = list(github_releases)
                            # Add any JSON versions not in GitHub (shouldn't happen usually)
                            for v in info.json_releases:
                                if v not in all_versions:
                                    all_versions.append(v)
                            info.available_versions = all_versions
            
            _status("Building object tree...")
            self._status_bar.showMessage(
                f"Loaded {local_count} local + {remote_count} remote objects",
                5000
            )
            
            # Populate the object tree from the cached resolved manifest
            self._tree_screen.populate_from_cache()
            
            _status("Finishing up...", f"{local_count} local + {remote_count} remote objects")
            # Start resolving git branches in background
            self._start_branch_resolver()
            
            # Start monitoring for file changes
            self._start_hash_checker()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._status_bar.showMessage(f"Error: {e}", 5000)

    # ------------------------------------------------------------------
    # Async loading (used by splash screen for smooth animation)
    # ------------------------------------------------------------------

    def _reload_async(self):
        """Reload the catalog asynchronously with a splash overlay.

        Creates a :class:`SplashScreen` centred over the main window,
        starts a :class:`LoaderThread`, and wires the signals so that
        the splash animates while heavy I/O runs in the background.
        """
        # Prevent overlapping reloads
        if getattr(self, "_is_loading", False):
            return
        self._is_loading = True

        # Stop the hash checker while we reload — it would otherwise
        # detect the manifest change and try to trigger another reload.
        self._stop_hash_checker()

        from .splash_screen import SplashScreen
        from .loader_thread import LoaderThread

        splash = SplashScreen()
        splash.show()
        splash.center_on(self)

        loader = LoaderThread(offline=self._offline)
        loader.statusChanged.connect(splash.set_status)

        def _on_ready(objects, store, lc, rc, resolved_data):
            self._apply_loaded_objects(objects, store, lc, rc, resolved_data)
            splash.finish()
            self._is_loading = False

        def _on_error(msg):
            splash.finish()
            self._is_loading = False
            self._status_bar.showMessage(f"Reload error: {msg}", 5000)
            # Restart hash checker even on error
            self._start_hash_checker()

        loader.objectsReady.connect(_on_ready)
        loader.loadError.connect(_on_error)

        # Prevent GC while the thread is running
        self._reload_loader = loader
        self._reload_splash = splash

        loader.start()

    def _apply_loaded_objects(self, objects, store, local_count, remote_count, resolved_data=None):
        """Apply objects collected by LoaderThread on the main thread.

        This is the slot connected to ``LoaderThread.objectsReady``.  It
        mirrors the tail end of :meth:`load_from_resolver` but receives
        pre-built :class:`ObjectInfo` instances so that no blocking I/O
        happens here.
        """
        self._catalog.clear()
        self._store = store

        for info in objects:
            self._catalog.add_object(info)

        self._status_bar.showMessage(
            f"Loaded {local_count} local + {remote_count} remote objects",
            5000,
        )

        # Populate the object tree using pre-loaded data (avoids re-resolving)
        self._tree_screen.populate_from_cache(resolved_data)

        # Rescan workspaces (new ones may have been created/registered)
        self._workspace_tab.refresh()

        # Start resolving git branches in background
        self._start_branch_resolver()

        # Start monitoring for file changes
        self._start_hash_checker()

    def _start_branch_resolver(self):
        """Start background thread to resolve git branches for objects without them."""
        # Stop any existing resolver
        if self._branch_resolver_thread and self._branch_resolver_thread.isRunning():
            if self._branch_resolver_worker:
                self._branch_resolver_worker.stop()
            self._branch_resolver_thread.quit()
            self._branch_resolver_thread.wait(1000)
        
        # Collect objects info — no I/O here, just read from the model
        local_objects = []
        objects_to_resolve = []
        model = self._catalog._model
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            info = model.data(index, ObjectRole.ObjectInfo)
            if info:
                # Queue local objects for git remote collection (done in worker)
                if info.is_local and info.path:
                    local_objects.append((str(info.path),))
                
                # For objects with repo URLs but no branch, queue for resolution
                if info.repository_url and not info.git_branch:
                    objects_to_resolve.append((
                        info.object_type.value,
                        info.name,
                        info.repository_url
                    ))
        
        if not objects_to_resolve:
            return
        
        # Create and start worker thread
        self._branch_resolver_thread = QThread()
        self._branch_resolver_worker = BranchResolverWorker(objects_to_resolve, local_objects)
        self._branch_resolver_worker.moveToThread(self._branch_resolver_thread)
        
        # Connect signals
        self._branch_resolver_thread.started.connect(self._branch_resolver_worker.run)
        self._branch_resolver_worker.branch_resolved.connect(self._on_branch_resolved)
        self._branch_resolver_worker.finished.connect(self._on_branch_resolver_finished)
        self._branch_resolver_worker.finished.connect(self._branch_resolver_thread.quit)
        
        self._branch_resolver_thread.start()
    
    def _on_branch_resolved(self, obj_type: str, name: str, branch: str, is_cloned: bool):
        """Handle branch resolution for an object."""
        # Find the object in the model and update its git_branch and clone status
        model = self._catalog._model
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            info = model.data(index, ObjectRole.ObjectInfo)
            if info and info.object_type.value == obj_type and info.name == name:
                if branch:
                    info.git_branch = branch
                info.is_repo_cloned = is_cloned
                # Trigger model update to repaint
                model.dataChanged.emit(index, index, [ObjectRole.ObjectInfo])
                break
    
    def _on_branch_resolver_finished(self):
        """Handle branch resolver completion."""
        # Cleanup is handled by signal connections
        pass
    
    def _start_hash_checker(self):
        """Start background thread to check for file changes periodically."""
        # Stop any existing hash checker
        if self._hash_checker_thread and self._hash_checker_thread.isRunning():
            if self._hash_checker_worker:
                self._hash_checker_worker.stop()
            self._hash_checker_thread.quit()
            self._hash_checker_thread.wait(1000)
        
        # Create and start worker
        self._hash_checker_thread = QThread()
        self._hash_checker_worker = HashCheckerWorker(check_interval_seconds=30)
        self._hash_checker_worker.moveToThread(self._hash_checker_thread)
        
        # Connect signals
        self._hash_checker_thread.started.connect(self._hash_checker_worker.run)
        self._hash_checker_worker.changes_detected.connect(self._on_files_changed)
        
        self._hash_checker_thread.start()
    
    def _stop_hash_checker(self):
        """Stop the hash checker background thread."""
        try:
            if self._hash_checker_thread and self._hash_checker_thread.isRunning():
                if self._hash_checker_worker:
                    self._hash_checker_worker.stop()
                self._hash_checker_thread.quit()
                self._hash_checker_thread.wait(2000)
        except RuntimeError:
            pass
    
    def _on_files_changed(self, changed_files: list):
        """Handle detected file changes - re-resolve and reload."""
        self._status_bar.showMessage(
            f"Detected changes in {len(changed_files)} file(s), reloading...", 3000
        )
        
        # Reload asynchronously — LoaderThread will re-resolve as needed
        self._reload_async()

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
            ),
            ObjectInfo(
                name="script-canvas",
                display_name="Script Canvas",
                object_type=ObjectType.GEM,
                version="1.0.0",
                origin=ObjectOrigin.LOCAL,
                summary="Visual scripting system for O3DE.",
                creator="O3DE Foundation",
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
        
        # Replace workspace tab with demo version
        idx = self._tabs.indexOf(self._workspace_tab)
        if idx >= 0:
            self._tabs.removeTab(idx)
            self._workspace_tab.deleteLater()
            self._workspace_tab = WorkspaceTab(demo=True)
            self._tabs.insertTab(idx, self._workspace_tab, "Workspaces")
