# O3DE Pilot GUI - Object Inspector
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Inspector panel for displaying object details.
This is analogous to GemInspector in the O3DE Project Manager.
"""

from typing import Optional
import threading
import httpx
from PySide6.QtCore import Qt, Signal, QModelIndex, QUrl
from PySide6.QtGui import QFont, QPixmap, QDesktopServices, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QComboBox
)

from .object_info import ObjectInfo, ObjectOrigin, DownloadStatus, Platform
from .object_model import ObjectModel, ObjectRole
from ..core import ObjectType


class ObjectInspector(QWidget):
    """
    Inspector panel showing detailed information about a selected object.
    
    Features:
    - Object icon and name
    - Version and type info
    - Summary and description
    - Dependencies
    - Platform support
    - Action buttons (add, remove, download)
    """
    
    # Icon constants
    ICON_SIZE = 48
    
    # Signals
    downloadClicked = Signal(QModelIndex)
    openDocumentation = Signal(str)
    openRepository = Signal(str)
    commandRequested = Signal(dict, object)  # (command_spec, ObjectInfo|None)
    
    # Icon cache (class-level shared cache)
    _icon_cache: dict[str, QPixmap] = {}
    _icon_loading: set[str] = set()
    
    def __init__(
        self,
        model: ObjectModel,
        read_only: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._model = model
        self._read_only = read_only
        self._current_index: Optional[QModelIndex] = None
        self._current_releases: dict = {}
        self._current_icon_key: str = ""  # Track which icon is displayed
        self._current_local_version: str = ""  # Track the locally installed version
        self._current_is_local: bool = False  # Track if object has local installation
        self._current_origin_url: str = ""  # Track the origin URL for local objects
        self._current_version: str = ""  # Track the currently displayed object version
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1A1A1A;
            }
            QScrollBar:vertical {
                background-color: #2D2D2D;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 4px;
            }
        """)
        
        # Content widget
        content = QWidget()
        content.setStyleSheet("background-color: #1A1A1A;")
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)
        
        # Header section (icon + name) - wrapped in container for centering
        header_container = QWidget()
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        # Icon - wrapped in container to ensure centering
        icon_container = QWidget()
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addStretch()
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(48, 48)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet("""
            QLabel {
                background-color: #2D2D2D;
                border-radius: 8px;
            }
        """)
        icon_layout.addWidget(self._icon_label)
        icon_layout.addStretch()
        header_layout.addWidget(icon_container)
        
        # Type badge
        self._type_label = QLabel()
        self._type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._type_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 7.5pt;
                font-weight: bold;
                padding: 4px 8px;
                background-color: #333333;
                border-radius: 3px;
            }
        """)
        header_layout.addWidget(self._type_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # Name
        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setMinimumWidth(0)
        self._name_label.setStyleSheet("color: #EEEEEE; font-size: 10pt; font-weight: bold;")
        header_layout.addWidget(self._name_label)
        
        # Version
        self._version_label = QLabel()
        self._version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._version_label.setStyleSheet("color: #888888; font-size: 8pt;")
        header_layout.addWidget(self._version_label)
        
        content_layout.addWidget(header_container)
        
        # Separator
        content_layout.addWidget(self._create_separator())
        
        # Action buttons - centered
        action_container = QWidget()
        self._action_layout = QHBoxLayout(action_container)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(8)
        
        self._download_button = QPushButton("Download")
        self._download_button.setStyleSheet(self._button_style("#00A0FC"))
        self._download_button.clicked.connect(self._on_download_clicked)
        self._action_layout.addWidget(self._download_button)
        
        self._unregister_button = QPushButton("Unregister")
        self._unregister_button.setStyleSheet(self._button_style("#FF9800"))
        self._unregister_button.clicked.connect(self._on_unregister_clicked)
        self._action_layout.addWidget(self._unregister_button)
        self._unregister_button.hide()
        
        self._action_layout.insertStretch(0)
        self._action_layout.addStretch()
        content_layout.addWidget(action_container)
        
        # Name selection (for remote objects with multiple versions)
        self._version_section = QHBoxLayout()
        self._version_section.setSpacing(8)
        
        version_select_label = QLabel("Name:")
        version_select_label.setStyleSheet("color: #888888; font-size: 8pt;")
        self._version_section.addWidget(version_select_label)
        
        self._version_combo = QComboBox()
        self._version_combo.setStyleSheet("""
            QComboBox {
                background-color: #3A3A3A;
                color: #EEEEEE;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 60px;
            }
            QComboBox:hover {
                border: 1px solid #00A0FC;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #888888;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #3A3A3A;
                color: #EEEEEE;
                selection-background-color: #00A0FC;
                border: 1px solid #555555;
            }
        """)
        self._version_combo.currentIndexChanged.connect(self._on_version_changed)
        self._version_section.addWidget(self._version_combo)
        self._version_section.addStretch()
        
        # Container widget for version section (so we can show/hide)
        self._version_container = QWidget()
        self._version_container.setLayout(self._version_section)
        content_layout.addWidget(self._version_container)
        
        # Download method selection (Git Clone vs Archive Download)
        self._method_section = QHBoxLayout()
        self._method_section.setSpacing(8)
        
        method_label = QLabel("Method:")
        method_label.setStyleSheet("color: #888888; font-size: 8pt;")
        self._method_section.addWidget(method_label)
        
        self._method_combo = QComboBox()
        self._method_combo.setStyleSheet(self._combo_style())
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._method_section.addWidget(self._method_combo)
        self._method_section.addStretch()
        
        self._method_container = QWidget()
        self._method_container.setLayout(self._method_section)
        content_layout.addWidget(self._method_container)
        
        # Option selection (for multiple downloads or source controls)
        self._option_section = QHBoxLayout()
        self._option_section.setSpacing(8)
        
        option_label = QLabel("Option:")
        option_label.setStyleSheet("color: #888888; font-size: 8pt;")
        self._option_section.addWidget(option_label)
        
        self._option_combo = QComboBox()
        self._option_combo.setStyleSheet(self._combo_style())
        self._option_section.addWidget(self._option_combo)
        self._option_section.addStretch()
        
        self._option_container = QWidget()
        self._option_container.setLayout(self._option_section)
        content_layout.addWidget(self._option_container)
        self._option_container.hide()  # Hidden by default
        
        # Connect option change to update details and button text
        self._option_combo.currentIndexChanged.connect(self._update_download_details)
        self._option_combo.currentIndexChanged.connect(self._update_download_button_text)
        
        # Download details display section
        self._details_section = QVBoxLayout()
        self._details_section.setSpacing(4)
        
        details_title = QLabel("Download Details")
        details_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 8pt;")
        self._details_section.addWidget(details_title)
        
        self._details_label = QLabel()
        self._details_label.setWordWrap(True)
        self._details_label.setMinimumWidth(0)
        self._details_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._details_label.setStyleSheet("color: #CCCCCC; font-size: 8pt; font-family: monospace;")
        self._details_section.addWidget(self._details_label)
        
        self._details_container = QWidget()
        self._details_container.setLayout(self._details_section)
        content_layout.addWidget(self._details_container)
        self._details_container.hide()  # Hidden by default
        
        # Separator
        content_layout.addWidget(self._create_separator())
        
        # Deprecation badge (hidden by default)
        self._deprecation_container = QWidget()
        deprecation_layout = QVBoxLayout(self._deprecation_container)
        deprecation_layout.setContentsMargins(0, 0, 0, 0)
        deprecation_layout.setSpacing(4)
        
        self._deprecation_badge = QLabel("DEPRECATED")
        self._deprecation_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deprecation_badge.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 7.5pt;
                font-weight: bold;
                padding: 4px 12px;
                background-color: #D32F2F;
                border-radius: 3px;
            }
        """)
        deprecation_layout.addWidget(self._deprecation_badge)
        
        self._deprecation_message = QLabel()
        self._deprecation_message.setWordWrap(True)
        self._deprecation_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deprecation_message.setStyleSheet("color: #FF8A80; font-size: 7.5pt;")
        deprecation_layout.addWidget(self._deprecation_message)
        
        self._deprecation_container.hide()
        content_layout.addWidget(self._deprecation_container)
        
        # Integrity indicator (hidden by default)
        self._integrity_container = QWidget()
        integrity_layout = QHBoxLayout(self._integrity_container)
        integrity_layout.setContentsMargins(0, 0, 0, 0)
        integrity_layout.setSpacing(6)
        integrity_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        
        self._integrity_icon = QLabel()
        self._integrity_icon.setStyleSheet("font-size: 9pt;")
        integrity_layout.addWidget(self._integrity_icon)
        
        self._integrity_label = QLabel()
        self._integrity_label.setStyleSheet("color: #888888; font-size: 7.5pt;")
        integrity_layout.addWidget(self._integrity_label)
        
        self._integrity_container.hide()
        content_layout.addWidget(self._integrity_container)
        
        # Summary section
        summary_section = QVBoxLayout()
        summary_section.setSpacing(4)
        
        summary_title = QLabel("Summary")
        summary_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 8pt;")
        summary_section.addWidget(summary_title)
        
        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setMinimumWidth(0)
        self._summary_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        summary_section.addWidget(self._summary_label)
        
        content_layout.addLayout(summary_section)
        
        # Origin section
        content_layout.addWidget(self._create_separator())
        
        origin_section = QVBoxLayout()
        origin_section.setSpacing(4)
        
        origin_title = QLabel("Origin")
        origin_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 8pt;")
        origin_section.addWidget(origin_title)
        
        self._creator_label = QLabel()
        self._creator_label.setWordWrap(True)
        self._creator_label.setMinimumWidth(0)
        self._creator_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        self._creator_label.setOpenExternalLinks(True)
        origin_section.addWidget(self._creator_label)
        
        self._origin_url_inline_label = QLabel()
        self._origin_url_inline_label.setWordWrap(True)
        self._origin_url_inline_label.setMinimumWidth(0)
        self._origin_url_inline_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        self._origin_url_inline_label.setOpenExternalLinks(True)
        origin_section.addWidget(self._origin_url_inline_label)
        
        content_layout.addLayout(origin_section)
        
        # Dependencies section
        content_layout.addWidget(self._create_separator())
        
        deps_section = QVBoxLayout()
        deps_section.setSpacing(4)
        
        deps_title = QLabel("Dependencies")
        deps_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 8pt;")
        deps_section.addWidget(deps_title)
        
        self._deps_label = QLabel()
        self._deps_label.setWordWrap(True)
        self._deps_label.setMinimumWidth(0)
        self._deps_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        deps_section.addWidget(self._deps_label)
        
        # Optional dependencies (hidden if empty)
        self._optional_deps_label = QLabel()
        self._optional_deps_label.setWordWrap(True)
        self._optional_deps_label.setMinimumWidth(0)
        self._optional_deps_label.setStyleSheet("color: #90CAF9; font-size: 8pt;")
        deps_section.addWidget(self._optional_deps_label)
        
        # Peer dependencies (hidden if empty)
        self._peer_deps_label = QLabel()
        self._peer_deps_label.setWordWrap(True)
        self._peer_deps_label.setMinimumWidth(0)
        self._peer_deps_label.setStyleSheet("color: #CE93D8; font-size: 8pt;")
        deps_section.addWidget(self._peer_deps_label)
        
        content_layout.addLayout(deps_section)
        
        # Platform section
        content_layout.addWidget(self._create_separator())
        
        platform_section = QVBoxLayout()
        platform_section.setSpacing(4)
        
        platform_title = QLabel("Platforms")
        platform_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 8pt;")
        platform_section.addWidget(platform_title)
        
        self._platform_label = QLabel()
        self._platform_label.setWordWrap(True)
        self._platform_label.setMinimumWidth(0)
        self._platform_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        platform_section.addWidget(self._platform_label)
        
        content_layout.addLayout(platform_section)
        
        # Links section
        content_layout.addWidget(self._create_separator())
        
        links_section = QVBoxLayout()
        links_section.setSpacing(4)
        
        links_title = QLabel("Links")
        links_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 8pt;")
        links_section.addWidget(links_title)
        
        self._doc_link_label = QLabel()
        self._doc_link_label.setWordWrap(True)
        self._doc_link_label.setMinimumWidth(0)
        self._doc_link_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        self._doc_link_label.setOpenExternalLinks(True)
        links_section.addWidget(self._doc_link_label)
        
        self._repo_link_label = QLabel()
        self._repo_link_label.setWordWrap(True)
        self._repo_link_label.setMinimumWidth(0)
        self._repo_link_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        self._repo_link_label.setOpenExternalLinks(True)
        links_section.addWidget(self._repo_link_label)
        
        content_layout.addLayout(links_section)
        
        # ── Details section (license, path, tags, etc.) ──────────────
        content_layout.addWidget(self._create_separator())

        details_section = QVBoxLayout()
        details_section.setSpacing(4)

        details_title = QLabel("Details")
        details_title.setStyleSheet(
            "color: #888888; font-weight: bold; font-size: 8pt;"
        )
        details_section.addWidget(details_title)

        # License
        self._license_label = QLabel()
        self._license_label.setWordWrap(True)
        self._license_label.setMinimumWidth(0)
        self._license_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        self._license_label.setOpenExternalLinks(True)
        details_section.addWidget(self._license_label)

        # Path
        self._path_label = QLabel()
        self._path_label.setWordWrap(True)
        self._path_label.setMinimumWidth(0)
        self._path_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        self._path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path_label.linkActivated.connect(self._on_path_clicked)
        details_section.addWidget(self._path_label)

        # Tags
        self._tags_label = QLabel()
        self._tags_label.setWordWrap(True)
        self._tags_label.setMinimumWidth(0)
        self._tags_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        details_section.addWidget(self._tags_label)

        # Compatible engines
        self._engines_label = QLabel()
        self._engines_label.setWordWrap(True)
        self._engines_label.setMinimumWidth(0)
        self._engines_label.setStyleSheet("color: #CCCCCC; font-size: 9pt;")
        details_section.addWidget(self._engines_label)

        content_layout.addLayout(details_section)

        # Add stretch
        content_layout.addStretch()
        
        scroll_area.setWidget(content)
        main_layout.addWidget(scroll_area)
        
        # Empty state
        self._empty_label = QLabel("Select an object to view details")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666666; font-size: 9pt;")
        main_layout.addWidget(self._empty_label)
        
        # Initially show empty state
        scroll_area.hide()
        self._scroll_area = scroll_area
    
    def _create_separator(self) -> QFrame:
        """Create a horizontal separator."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #333333;")
        line.setFixedHeight(1)
        return line
    
    def _button_style(self, color: str) -> str:
        """Get button style with given color."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: 2px solid transparent;
                border-radius: 4px;
                padding: 4px 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 2px solid #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #FFFFFF;
                color: #333333;
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: #888888;
            }}
        """
    
    def _combo_style(self) -> str:
        """Get combo box style."""
        return """
            QComboBox {
                background-color: #3A3A3A;
                color: #EEEEEE;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 60px;
            }
            QComboBox:hover {
                border: 1px solid #00A0FC;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #888888;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #3A3A3A;
                color: #EEEEEE;
                selection-background-color: #00A0FC;
                border: 1px solid #555555;
            }
        """
    
    def _on_method_changed(self, index: int):
        """Handle download method selection change - update option dropdown."""
        method = self._method_combo.currentData()
        version = self._version_combo.currentData() or self._current_version
        
        if not version or version not in self._current_releases:
            self._option_container.hide()
            self._details_container.hide()
            return
        
        release = self._current_releases[version]
        self._option_combo.clear()
        
        if method == "git":
            # Populate with source_controls options
            source_controls = release.get('source_controls', [])
            if isinstance(source_controls, list) and len(source_controls) > 1:
                for i, sc in enumerate(source_controls):
                    self._option_combo.addItem(str(i + 1), i)
                self._option_container.show()
            else:
                self._option_container.hide()
        elif method == "archive":
            # Populate with downloads options that have source/lfs
            downloads = release.get('downloads', [])
            if isinstance(downloads, list):
                archive_options = [(i, dl) for i, dl in enumerate(downloads) if dl.get('source') or dl.get('lfs')]
                if len(archive_options) > 1:
                    for idx, (i, dl) in enumerate(archive_options):
                        self._option_combo.addItem(str(idx + 1), i)
                    self._option_container.show()
                else:
                    self._option_container.hide()
            else:
                self._option_container.hide()
        elif method == "binary":
            # Populate with binaries options (separate array with platform info)
            binaries = release.get('binaries', [])
            if isinstance(binaries, list) and len(binaries) > 0:
                if len(binaries) > 1:
                    for i, binary_item in enumerate(binaries):
                        # Show platform as label, fall back to index
                        platform = binary_item.get('platform', str(i + 1))
                        self._option_combo.addItem(platform, i)
                    self._option_container.show()
                else:
                    self._option_container.hide()
            else:
                self._option_container.hide()
        else:
            self._option_container.hide()
        
        # Update the download details display
        self._update_download_details()
    
    def _update_download_details(self):
        """Update the download details display based on current selections."""
        urls = self.get_download_urls()
        if not urls:
            self._details_container.hide()
            return
        
        method = self.get_selected_method()
        lines = []
        
        if method == "git":
            if urls.get('git'):
                lines.append(f"Repository: {urls['git']}")
            if urls.get('tag'):
                lines.append(f"Tag: {urls['tag']}")
            if urls.get('branch'):
                lines.append(f"Branch: {urls['branch']}")
        elif method == "archive":
            if urls.get('source'):
                lines.append(f"Source: {urls['source']}")
            if urls.get('lfs'):
                lines.append(f"LFS: {urls['lfs']}")
        elif method == "binary":
            if urls.get('platform'):
                lines.append(f"Platform: {urls['platform']}")
            if urls.get('binary'):
                lines.append(f"Binary: {urls['binary']}")
        
        if lines:
            self._details_label.setText("\n".join(lines))
            self._details_container.show()
        else:
            self._details_container.hide()
    
    def _get_cached_icon(self, key: str) -> Optional[QPixmap]:
        """Get icon from cache."""
        return self._icon_cache.get(key)
    
    def _load_icon_from_url(self, url: str):
        """Load icon from URL asynchronously."""
        if url in self._icon_cache or url in self._icon_loading:
            return
        
        self._icon_loading.add(url)
        
        def load():
            try:
                response = httpx.get(url, timeout=10, follow_redirects=True)
                if response.status_code == 200:
                    image = QImage()
                    if image.loadFromData(response.content):
                        pixmap = QPixmap.fromImage(image).scaled(
                            self.ICON_SIZE, self.ICON_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self._icon_cache[url] = pixmap
                        # Update icon if this is still the current object
                        if self._current_icon_key == url:
                            self._apply_icon_pixmap(pixmap)
            except Exception:
                pass
            finally:
                self._icon_loading.discard(url)
        
        thread = threading.Thread(target=load, daemon=True)
        thread.start()
    
    def _load_icon_from_path(self, path) -> Optional[QPixmap]:
        """Load icon from local path."""
        cache_key = str(path)
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        
        if path.exists():
            loaded = QPixmap(str(path))
            if not loaded.isNull():
                pixmap = loaded.scaled(
                    self.ICON_SIZE, self.ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._icon_cache[cache_key] = pixmap
                return pixmap
        return None
    
    def _apply_icon_pixmap(self, pixmap: QPixmap):
        """Apply pixmap to the icon label."""
        self._icon_label.setStyleSheet("""
            QLabel {
                background-color: #2D2D2D;
                border-radius: 8px;
            }
        """)
        self._icon_label.setText("")
        self._icon_label.setPixmap(pixmap)
    
    def _apply_icon_placeholder(self, info: ObjectInfo):
        """Apply the default type placeholder icon."""
        type_color = {
            ObjectType.ENGINE: "#FF9800",
            ObjectType.PROJECT: "#2196F3",
            ObjectType.GEM: "#9C27B0",
            ObjectType.TEMPLATE: "#00BCD4",
            ObjectType.REPO: "#4CAF50",
            ObjectType.OVERLAY: "#FF5722",
        }.get(info.object_type, "#888888")
        
        self._icon_label.setPixmap(QPixmap())  # Clear any existing pixmap
        self._icon_label.setStyleSheet(f"""
            QLabel {{
                background-color: {type_color}33;
                border: 2px solid {type_color};
                border-radius: 8px;
                color: {type_color};
                font-size: 24pt;
                font-weight: bold;
            }}
        """)
        self._icon_label.setText(info.object_type.value[0].upper())
    
    def _on_version_changed(self, index: int):
        """Handle version selection change - update method dropdown."""
        version = self._version_combo.currentData()
        if not version or version not in self._current_releases:
            self._method_container.hide()
            self._option_container.hide()
            return
        
        release = self._current_releases[version]
        
        # Check source_controls (array, new format) or source_control (object, old format)
        source_controls = release.get('source_controls', [])
        source_control = release.get('source_control', {})
        has_source_control = bool(source_controls) or bool(source_control.get('git') or source_control.get('git_uri'))
        
        # Check downloads (array, new format) or old format
        downloads = release.get('downloads', [])
        has_archive = False
        if isinstance(downloads, list) and downloads:
            for dl in downloads:
                if dl.get('source') or dl.get('lfs'):
                    has_archive = True
        elif isinstance(downloads, dict):
            has_archive = bool(downloads)
        
        # Check binaries (separate array with platform info)
        binaries = release.get('binaries', [])
        has_binary = bool(binaries) and isinstance(binaries, list)
        
        # Block signals while updating to prevent multiple _on_method_changed calls
        self._method_combo.blockSignals(True)
        self._method_combo.clear()
        if has_source_control:
            self._method_combo.addItem("Git Clone", "git")
        if has_archive:
            self._method_combo.addItem("Code Archive", "archive")
        if has_binary:
            self._method_combo.addItem("Binary", "binary")
        self._method_combo.blockSignals(False)
        
        show_method = has_source_control or has_archive or has_binary
        self._method_container.setVisible(show_method)
        
        # Update option dropdown based on method
        self._on_method_changed(0)
        
        # Update download button text (Download vs Refresh)
        self._update_download_button_text()
    
    def _update_download_button_text(self):
        """Update download/refresh button text and all button visibility based on selected version and source."""
        selected_version = self._version_combo.currentData()
        if not selected_version:
            selected_version = self._current_local_version
        
        is_selected_version_local = (
            self._current_is_local and 
            selected_version == self._current_local_version
        )
        
        # Also check if the selected source URL matches the local origin URL
        is_same_source = True
        if is_selected_version_local:
            method = self.get_selected_method()
            if method == "git":
                urls = self.get_download_urls()
                selected_git_url = urls.get('git', '')
                # Normalize URLs for comparison (strip trailing slashes, .git suffix)
                def normalize_git_url(url: str) -> str:
                    url = url.rstrip('/')
                    if url.endswith('.git'):
                        url = url[:-4]
                    return url.lower()
                
                if selected_git_url and self._current_origin_url:
                    is_same_source = normalize_git_url(selected_git_url) == normalize_git_url(self._current_origin_url)
        
        # Update button text and visibility
        if is_selected_version_local and is_same_source:
            # Local version and same source: show Refresh and Remove, hide Add/Download
            self._download_button.setText("Refresh")
            self._download_button.show()
        else:
            # Different version or different source: show Download
            self._download_button.setText("Download")
            self._download_button.show()
        
        # Update version combo text color (green for local)
        self._update_version_combo_colors()
    
    def _update_version_combo_colors(self):
        """Update version combo item colors - green for local version."""
        from PySide6.QtGui import QColor
        from PySide6.QtCore import Qt
        
        local_color = QColor("#4CAF50")  # Green for local
        remote_color = QColor("#EEEEEE")  # Default white for remote
        
        for i in range(self._version_combo.count()):
            version = self._version_combo.itemData(i)
            if self._current_is_local and version == self._current_local_version:
                self._version_combo.setItemData(i, local_color, Qt.ItemDataRole.ForegroundRole)
            else:
                self._version_combo.setItemData(i, remote_color, Qt.ItemDataRole.ForegroundRole)
        
        # Update the combo box current text color
        selected_version = self._version_combo.currentData()
        if self._current_is_local and selected_version == self._current_local_version:
            self._version_combo.setStyleSheet(self._version_combo_style("#4CAF50"))
        else:
            self._version_combo.setStyleSheet(self._version_combo_style("#EEEEEE"))
    
    def _version_combo_style(self, text_color: str) -> str:
        """Get version combo style with specified text color."""
        return f"""
            QComboBox {{
                background-color: #3A3A3A;
                color: {text_color};
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 60px;
            }}
            QComboBox:hover {{
                border: 1px solid #00A0FC;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #888888;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #3A3A3A;
                color: #EEEEEE;
                selection-background-color: #00A0FC;
                border: 1px solid #555555;
            }}
        """
    
    def update_from_index(self, index: QModelIndex):
        """Update the inspector with data from a model index."""
        if not index.isValid():
            self._show_empty_state()
            return
        
        self._current_index = index
        info: ObjectInfo = self._model.get_object_info(index)
        
        if not info:
            self._show_empty_state()
            return
        
        self._show_content()
        self._update_content(info)
    
    def _show_empty_state(self):
        """Show the empty state."""
        self._scroll_area.hide()
        self._empty_label.show()
        self._current_index = None
    
    def _show_content(self):
        """Show the content area."""
        self._empty_label.hide()
        self._scroll_area.show()
    
    def _update_content(self, info: ObjectInfo):
        """Update content with object info."""
        # Update icon - try to load actual icon, fall back to placeholder
        pixmap = None
        icon_key = ""
        
        if info.is_remote:
            # Remote: try URL only
            if info.icon_url:
                icon_key = info.icon_url
                pixmap = self._get_cached_icon(info.icon_url)
                if not pixmap:
                    self._load_icon_from_url(info.icon_url)
        else:
            # Local: try local file first, then URL fallback
            if info.icon_path and info.icon_path.exists():
                icon_key = str(info.icon_path)
                pixmap = self._load_icon_from_path(info.icon_path)
            
            # Fallback to URL if local icon not found
            if not pixmap and info.icon_url:
                icon_key = info.icon_url
                pixmap = self._get_cached_icon(info.icon_url)
                if not pixmap:
                    self._load_icon_from_url(info.icon_url)
        
        self._current_icon_key = icon_key
        
        if pixmap:
            self._apply_icon_pixmap(pixmap)
        else:
            self._apply_icon_placeholder(info)
        
        # Type badge
        self._type_label.setText(info.object_type.value.upper())
        
        # Name
        self._name_label.setText(info.display_name)
        
        # Version/Name
        self._version_label.setText(info.version)
        
        # Deprecation badge
        if info.is_deprecated:
            self._deprecation_container.show()
            msg_parts = []
            if info.deprecation_message:
                msg_parts.append(info.deprecation_message)
            if info.replacement_name:
                msg_parts.append(f"Use {info.replacement_name} instead.")
            self._deprecation_message.setText(" ".join(msg_parts) if msg_parts else "")
            self._deprecation_message.setVisible(bool(msg_parts))
        else:
            self._deprecation_container.hide()
        
        # Integrity indicator
        if info.has_integrity:
            self._integrity_icon.setText("\u2705")  # checkmark
            self._integrity_label.setText(f"Integrity verified ({info.integrity_algorithm or 'sha256'})")
            self._integrity_container.show()
        else:
            self._integrity_icon.setText("\u26A0")  # warning
            self._integrity_label.setText("No integrity checksums")
            self._integrity_container.show()
        
        # Summary
        self._summary_label.setText(info.summary or "No summary provided.")
        
        # Origin
        creator_name = info.creator or "Unknown"
        self._creator_label.setTextFormat(Qt.TextFormat.PlainText)
        self._creator_label.setText(creator_name)
        
        if info.origin_url:
            breakable_url = info.origin_url.replace("/", "/\u200B")
            self._origin_url_inline_label.setTextFormat(Qt.TextFormat.RichText)
            self._origin_url_inline_label.setText(
                f'<span style="word-break:break-all"><a style="color:#58a6ff" href="{info.origin_url}">{breakable_url}</a></span>'
            )
            self._origin_url_inline_label.show()
        else:
            self._origin_url_inline_label.hide()
        
        # Dependencies – colour-coded by resolution status
        if info.dependencies:
            self._deps_label.setTextFormat(Qt.TextFormat.RichText)
            dep_spans = []
            for dep_str in info.dependencies:
                status = self._model.dependency_status(dep_str)
                if status == "local":
                    color = "#66BB6A"   # green
                elif status == "known":
                    color = "#42A5F5"   # blue
                else:
                    color = "#EF5350"   # red
                dep_spans.append(f'<span style="color:{color}">{dep_str}</span>')
            self._deps_label.setText(", ".join(dep_spans))
        else:
            self._deps_label.setTextFormat(Qt.TextFormat.PlainText)
            self._deps_label.setText("None")
        
        # Optional dependencies
        if info.optional_dependencies:
            self._optional_deps_label.setText("Optional: " + ", ".join(info.optional_dependencies))
            self._optional_deps_label.show()
        else:
            self._optional_deps_label.hide()
        
        # Peer dependencies
        if info.peer_dependencies:
            self._peer_deps_label.setText("Peer: " + ", ".join(info.peer_dependencies))
            self._peer_deps_label.show()
        else:
            self._peer_deps_label.hide()
        
        # Platforms
        platforms = []
        if info.platforms & Platform.WINDOWS:
            platforms.append("Windows")
        if info.platforms & Platform.LINUX:
            platforms.append("Linux")
        if info.platforms & Platform.MACOS:
            platforms.append("macOS")
        if info.platforms & Platform.ANDROID:
            platforms.append("Android")
        if info.platforms & Platform.IOS:
            platforms.append("iOS")
        self._platform_label.setText(", ".join(platforms) if platforms else "All Platforms")
        
        # Action buttons
        if self._read_only:
            self._download_button.hide()
            self._unregister_button.hide()
            self._version_container.hide()
            self._method_container.hide()
        else:
            # Track local version for Refresh detection
            self._current_local_version = info.version
            self._current_is_local = not info.is_remote or info.download_status == DownloadStatus.DOWNLOADED
            self._current_origin_url = info.origin_url or ""
            
            # Unregister button - show only for directly manifest-registered objects
            self._unregister_button.setVisible(info.is_manifest_registered)
            
            # Update button text and visibility based on selected version
            # (will be called again after version combo is populated)
            self._update_download_button_text()
            
            # Version dropdown - show for objects with multiple versions (remote or local releases)
            self._version_combo.clear()
            if info.available_versions and len(info.available_versions) > 1:
                for version in info.available_versions:
                    self._version_combo.addItem(version, version)
                # Select the current version if it's in the list
                if info.version in info.available_versions:
                    idx = info.available_versions.index(info.version)
                    self._version_combo.setCurrentIndex(idx)
                self._version_container.show()
            else:
                self._version_container.hide()
            
            # Method dropdown - populate based on release data
            self._method_combo.blockSignals(True)
            self._method_combo.clear()
            self._current_releases = info.releases
            self._current_version = info.version
            selected_version = self._version_combo.currentData() or info.version
            release_data = info.releases.get(selected_version, {})
            
            # Check source_controls (array, new format) or source_control (object, old format)
            source_controls = release_data.get('source_controls', [])
            source_control = release_data.get('source_control', {})
            has_source_control = bool(source_controls) or bool(source_control.get('git') or source_control.get('git_uri'))
            
            # Check downloads (array, new format) or old format
            downloads = release_data.get('downloads', [])
            has_downloads = bool(downloads) if isinstance(downloads, list) else bool(downloads)
            
            # Check binaries (separate array with platform info)
            binaries = release_data.get('binaries', [])
            has_binary = bool(binaries) and isinstance(binaries, list)
            
            if has_source_control:
                self._method_combo.addItem("Git Clone", "git")
            if has_downloads:
                self._method_combo.addItem("Code Archive", "archive")
            if has_binary:
                self._method_combo.addItem("Binary", "binary")
            self._method_combo.blockSignals(False)
            
            # Show method dropdown if there are options
            show_method = len(info.releases) > 0 and (has_source_control or has_downloads or has_binary)
            self._method_container.setVisible(show_method)
            
            # Update option dropdown and download details
            self._on_method_changed(0)
        
        # Links
        if info.documentation_url:
            breakable_doc = info.documentation_url.replace("/", "/\u200B")
            self._doc_link_label.setTextFormat(Qt.TextFormat.RichText)
            self._doc_link_label.setText(
                f'<span style="word-break:break-all">Documentation: <a style="color:#58a6ff" href="{info.documentation_url}">{breakable_doc}</a></span>'
            )
            self._doc_link_label.show()
        else:
            self._doc_link_label.hide()
        
        if info.repository_url:
            breakable_repo = info.repository_url.replace("/", "/\u200B")
            branch_suffix = f" ({info.git_branch})" if info.git_branch else ""
            self._repo_link_label.setTextFormat(Qt.TextFormat.RichText)
            self._repo_link_label.setText(
                f'<span style="word-break:break-all">Repository: <a style="color:#58a6ff" href="{info.repository_url}">{breakable_repo}</a>{branch_suffix}</span>'
            )
            self._repo_link_label.show()
        else:
            self._repo_link_label.hide()

        # Details section (license, path, tags, etc.)
        self._update_details(info)
    
    def _on_download_clicked(self):
        """Handle download button click."""
        if self._current_index and self._current_index.isValid():
            self.downloadClicked.emit(self._current_index)
    
    def _on_unregister_clicked(self):
        """Handle unregister button click — emit commandRequested for
        the 'unregister local' spec with the current object."""
        from .command_specs import COMMAND_SPECS

        if not (self._current_index and self._current_index.isValid()):
            return
        info: ObjectInfo = self._model.get_object_info(self._current_index)
        if info is None:
            return
        spec = COMMAND_SPECS.get("unregister local")
        if spec:
            self.commandRequested.emit(spec, info)
    
    def _on_path_clicked(self, url: str):
        """Open the object's directory in the system file explorer."""
        QDesktopServices.openUrl(QUrl(url))

    # ── Details section ────────────────────────────────────────────

    def _update_details(self, info: ObjectInfo):
        """Populate the details section with license, path, tags, etc."""
        # License(s)
        all_licenses = info.licenses if info.licenses else []
        if not all_licenses and info.license_text:
            all_licenses = [{"text": info.license_text, "url": info.license_url}]
        
        if all_licenses:
            self._license_label.setTextFormat(Qt.TextFormat.RichText)
            parts = []
            for lic in all_licenses:
                lic_text = lic.get("text", "")
                lic_url = lic.get("url", "")
                if lic_text:
                    if lic_url:
                        parts.append(f'<a style="color:#58a6ff" href="{lic_url}">{lic_text}</a>')
                    else:
                        parts.append(lic_text)
            if parts:
                self._license_label.setText("License: " + ", ".join(parts))
                self._license_label.show()
            else:
                self._license_label.hide()
        else:
            self._license_label.hide()

        # Path
        if info.path:
            path_str = str(info.path)
            # Insert zero-width spaces after path separators so word-wrap can break there
            breakable_path = path_str.replace("\\", "\\\u200B").replace("/", "/\u200B")
            file_url = QUrl.fromLocalFile(path_str).toString()
            self._path_label.setTextFormat(Qt.TextFormat.RichText)
            self._path_label.setText(
                f'<span style="word-break:break-all">Path: <a style="color:#58a6ff" href="{file_url}">{breakable_path}</a></span>'
            )
            self._path_label.show()
        else:
            self._path_label.hide()

        # Tags
        if info.tags:
            self._tags_label.setText(f"Tags: {', '.join(info.tags)}")
            self._tags_label.show()
        else:
            self._tags_label.hide()

        # Compatible engines
        if info.compatible_engines:
            self._engines_label.setText(
                f"Engines: {', '.join(info.compatible_engines)}"
            )
            self._engines_label.show()
        else:
            self._engines_label.hide()
    
    def get_selected_version(self) -> Optional[str]:
        """Get the currently selected version from the dropdown.
        
        Returns:
            The selected version string, or None if no version selected.
        """
        if self._version_combo.currentIndex() >= 0:
            return self._version_combo.currentData()
        return self._current_version or None
    
    def get_selected_method(self) -> Optional[str]:
        """Get the currently selected download method.
        
        Returns:
            'git' for Git Clone, 'archive' for Code Archive, 'binary' for Binary, or None.
        """
        if self._method_combo.currentIndex() >= 0:
            return self._method_combo.currentData()
        return None
    
    def get_download_urls(self) -> dict:
        """Get the download URLs for the selected version/method.
        
        New schema format:
        - downloads: array of {source, lfs} objects (code archives only)
        - binaries: array of {platform, binary} objects (platform-specific binaries)
        - source_controls: array of {git, branch, tag} objects
        
        Returns:
            Dict with 'git', 'tag', 'branch' for git method,
            'source', 'lfs' for archive method, or
            'platform', 'binary' for binary method.
        """
        version = self.get_selected_version()
        if not version or version not in self._current_releases:
            return {}
        
        release = self._current_releases[version]
        method = self.get_selected_method()
        
        if method == "git":
            # Try new format: source_controls array
            source_controls = release.get('source_controls', [])
            if source_controls and len(source_controls) > 0:
                # Get selected option index from combo, default to 0
                option_idx = self._option_combo.currentData()
                if option_idx is None or not isinstance(option_idx, int):
                    option_idx = 0
                option_idx = min(option_idx, len(source_controls) - 1)
                sc = source_controls[option_idx]
                return {
                    'git': sc.get('git', ''),
                    'tag': sc.get('tag', ''),
                    'branch': sc.get('branch', ''),
                }
            # Fallback to old format: source_control object
            sc = release.get('source_control', {})
            return {
                'git': sc.get('git') or sc.get('git_uri', ''),
                'tag': sc.get('tag', ''),
                'branch': sc.get('branch', ''),
            }
        elif method == "archive":
            downloads = release.get('downloads', [])
            
            # New format: downloads is array of {source, lfs, binary}
            if isinstance(downloads, list) and len(downloads) > 0:
                # Get selected option index from combo, default to 0
                option_idx = self._option_combo.currentData()
                if option_idx is None or not isinstance(option_idx, int):
                    option_idx = 0
                option_idx = min(option_idx, len(downloads) - 1)
                dl = downloads[option_idx]
                return {
                    'source': dl.get('source', ''),
                    'lfs': dl.get('lfs', ''),
                }
            # Old format: downloads is object with source_zip_uri, lfs_zip_uri, etc.
            elif isinstance(downloads, dict):
                # Try to find zip first, then targz
                source_url = downloads.get('source_zip_uri') or downloads.get('source_targz_uri', '')
                lfs_url = downloads.get('lfs_zip_uri') or downloads.get('lfs_targz_uri', '')
                return {
                    'source': source_url,
                    'lfs': lfs_url,
                }
        elif method == "binary":
            binaries = release.get('binaries', [])
            
            if isinstance(binaries, list) and len(binaries) > 0:
                # Get selected option index from combo, default to 0
                option_idx = self._option_combo.currentData()
                if option_idx is None or not isinstance(option_idx, int):
                    option_idx = 0
                option_idx = min(option_idx, len(binaries) - 1)
                binary_item = binaries[option_idx]
                return {
                    'platform': binary_item.get('platform', ''),
                    'binary': binary_item.get('binary', ''),
                }
        return {}
    
    def set_download_enabled(self, enabled: bool):
        """Enable or disable the download button (for offline mode).
        
        Args:
            enabled: If True, enable download; if False, disable.
        """
        self._download_button.setEnabled(enabled)
        if not enabled:
            self._download_button.setToolTip("Download disabled - no internet connection")
        else:
            self._download_button.setToolTip("")
