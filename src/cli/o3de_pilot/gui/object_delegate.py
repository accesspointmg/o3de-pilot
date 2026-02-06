# O3DE Pilot GUI - Object Item Delegate
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Custom delegate for rendering objects in the catalog list.
This is analogous to GemItemDelegate in the O3DE Project Manager.
"""

from typing import Optional
from pathlib import Path
import threading
import httpx
from PySide6.QtCore import Qt, QRect, QSize, QModelIndex, QRectF, QObject, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QFontMetrics, QPixmap, QIcon,
    QPainterPath, QBrush, QImage
)
from PySide6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
)

from .object_info import ObjectInfo, ObjectOrigin, DownloadStatus, Platform
from .object_model import ObjectRole
from ..core import ObjectType


class ObjectItemDelegate(QStyledItemDelegate):
    """
    Custom delegate for rendering O3DE objects in list view.
    
    Features:
    - Object icon/preview image
    - Name with type indicator
    - Summary text
    - Version display
    - Status indicators (added, downloaded, etc.)
    - Platform icons
    """
    
    # Layout constants
    ITEM_HEIGHT = 90
    ITEM_MARGIN = 8
    ICON_SIZE = 64
    CORNER_RADIUS = 6
    BORDER_WIDTH = 2
    FONT_SIZE = 12
    FONT_SIZE_SMALL = 10
    STATUS_ICON_SIZE = 20
    BUTTON_WIDTH = 80
    BUTTON_HEIGHT = 28
    
    # Colors (O3DE dark theme)
    COLOR_BACKGROUND = QColor(34, 34, 34)       # #222222
    COLOR_ITEM_BG = QColor(45, 45, 45)          # #2D2D2D
    COLOR_ITEM_HOVER = QColor(55, 55, 55)       # #373737
    COLOR_ITEM_SELECTED = QColor(65, 65, 65)    # #414141
    COLOR_BORDER = QColor(0, 160, 252)          # O3DE blue
    COLOR_TEXT = QColor(230, 230, 230)          # Light gray
    COLOR_TEXT_DIM = QColor(160, 160, 160)      # Dim gray
    COLOR_TEXT_MUTED = QColor(120, 120, 120)    # Muted gray
    COLOR_ADDED = QColor(76, 175, 80)           # Green
    COLOR_REMOTE = QColor(255, 193, 7)          # Amber
    COLOR_ERROR = QColor(244, 67, 54)           # Red
    
    # Type colors
    TYPE_COLORS = {
        ObjectType.ENGINE: QColor(255, 152, 0),    # Orange
        ObjectType.PROJECT: QColor(33, 150, 243),  # Blue
        ObjectType.GEM: QColor(156, 39, 176),      # Purple
        ObjectType.TEMPLATE: QColor(0, 188, 212),  # Cyan
        ObjectType.REPO: QColor(76, 175, 80),      # Green
        ObjectType.OVERLAY: QColor(255, 87, 34),   # Deep Orange
    }
    
    # Icon cache (class-level shared cache)
    _icon_cache: dict[str, QPixmap] = {}
    _icon_loading: set[str] = set()
    
    def __init__(self, parent=None, read_only: bool = False):
        super().__init__(parent)
        self._read_only = read_only
        self._hovered_row = -1
        
        # Load icons
        self._setup_icons()
    
    def _setup_icons(self):
        """Set up status and platform icons."""
        # These would normally load from resources
        # For now, we'll draw simple shapes
        pass
    
    def _get_cached_icon(self, url: str) -> Optional[QPixmap]:
        """Get icon from cache or start loading."""
        if url in self._icon_cache:
            return self._icon_cache[url]
        
        # Start async loading if not already loading
        if url not in self._icon_loading:
            self._icon_loading.add(url)
            self._load_icon_async(url)
        
        return None
    
    def _load_icon_async(self, url: str):
        """Load icon from URL asynchronously."""
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
            except Exception:
                pass
            finally:
                self._icon_loading.discard(url)
        
        thread = threading.Thread(target=load, daemon=True)
        thread.start()
    
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Return the size hint for an item."""
        return QSize(option.rect.width(), self.ITEM_HEIGHT + self.ITEM_MARGIN)
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """Paint an item in the list view."""
        if not index.isValid():
            return
        
        # Get object info
        info: ObjectInfo = index.data(ObjectRole.ObjectInfo)
        if not info:
            return
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate rects
        full_rect = option.rect
        item_rect = QRect(
            full_rect.left() + self.ITEM_MARGIN,
            full_rect.top() + self.ITEM_MARGIN // 2,
            full_rect.width() - self.ITEM_MARGIN * 2,
            full_rect.height() - self.ITEM_MARGIN
        )
        
        # Draw background
        painter.fillRect(full_rect, self.COLOR_BACKGROUND)
        
        # Determine item background color
        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = self.COLOR_ITEM_SELECTED
        elif option.state & QStyle.StateFlag.State_MouseOver:
            bg_color = self.COLOR_ITEM_HOVER
        else:
            bg_color = self.COLOR_ITEM_BG
        
        # Draw item background with rounded corners
        path = QPainterPath()
        path.addRoundedRect(QRectF(item_rect), self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.fillPath(path, bg_color)
        
        # Draw selection border
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(self.COLOR_BORDER, self.BORDER_WIDTH))
            painter.drawPath(path)
        
        # Content area
        content_left = item_rect.left() + self.ITEM_MARGIN
        content_top = item_rect.top() + self.ITEM_MARGIN
        content_right = item_rect.right() - self.ITEM_MARGIN
        
        # Draw icon placeholder
        icon_rect = QRect(
            content_left,
            content_top,
            self.ICON_SIZE,
            self.ICON_SIZE
        )
        self._draw_icon(painter, icon_rect, info)
        
        # Text area (after icon)
        text_left = icon_rect.right() + self.ITEM_MARGIN * 2
        text_width = content_right - text_left - self.BUTTON_WIDTH - self.ITEM_MARGIN
        
        # Draw type badge
        type_color = self.TYPE_COLORS.get(info.object_type, self.COLOR_TEXT_DIM)
        badge_rect = self._draw_type_badge(painter, text_left, content_top, info.object_type, type_color)
        
        # Draw origin badge (Remote/Local) if remote
        origin_x = badge_rect.right() + 6
        if info.is_remote:
            origin_rect = self._draw_origin_badge(painter, origin_x, content_top, "REMOTE", self.COLOR_REMOTE)
        
        # Draw name
        name_top = content_top + badge_rect.height() + 4
        self._draw_name(painter, text_left, name_top, text_width, info)
        
        # Draw summary
        summary_top = name_top + 20
        self._draw_summary(painter, text_left, summary_top, text_width, info)
        
        # Draw version
        version_rect = QRect(
            content_right - self.BUTTON_WIDTH - 80,
            content_top + (item_rect.height() - 24) // 2,
            70,
            24
        )
        self._draw_version(painter, version_rect, info)
        
        # Draw status/action button area
        button_rect = QRect(
            content_right - self.BUTTON_WIDTH,
            content_top + (item_rect.height() - self.BUTTON_HEIGHT) // 2,
            self.BUTTON_WIDTH,
            self.BUTTON_HEIGHT
        )
        self._draw_status(painter, button_rect, info)
        
        painter.restore()
    
    def _draw_icon(self, painter: QPainter, rect: QRect, info: ObjectInfo):
        """Draw the object icon or placeholder.
        
        Fallback logic:
        - Remote objects: icon_url → default placeholder
        - Local objects: icon_path (from relative_path) → icon_url → default placeholder
        """
        type_color = self.TYPE_COLORS.get(info.object_type, self.COLOR_TEXT_DIM)
        pixmap = None
        
        if info.is_remote:
            # Remote: try URL only
            if info.icon_url:
                pixmap = self._get_cached_icon(info.icon_url)
        else:
            # Local: try local file first, then URL fallback
            if info.icon_path and info.icon_path.exists():
                cache_key = str(info.icon_path)
                if cache_key in self._icon_cache:
                    pixmap = self._icon_cache[cache_key]
                else:
                    loaded = QPixmap(str(info.icon_path))
                    if not loaded.isNull():
                        pixmap = loaded.scaled(
                            self.ICON_SIZE, self.ICON_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self._icon_cache[cache_key] = pixmap
            
            # Fallback to URL if local icon not found
            if not pixmap and info.icon_url:
                pixmap = self._get_cached_icon(info.icon_url)
        
        if pixmap and not pixmap.isNull():
            # Draw actual icon with rounded corners
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 4, 4)
            painter.setClipPath(path)
            # Center the pixmap in the rect
            x = rect.left() + (rect.width() - pixmap.width()) // 2
            y = rect.top() + (rect.height() - pixmap.height()) // 2
            painter.drawPixmap(x, y, pixmap)
            painter.setClipping(False)
        else:
            # Draw placeholder icon based on type
            # Draw rounded rectangle background
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 4, 4)
            painter.fillPath(path, type_color.darker(200))
            
            # Draw type initial in center
            painter.setPen(type_color)
            font = QFont()
            font.setPixelSize(24)
            font.setBold(True)
            painter.setFont(font)
            
            initial = info.object_type.value[0].upper()
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initial)
    
    def _draw_type_badge(self, painter: QPainter, x: int, y: int, 
                         object_type: ObjectType, color: QColor) -> QRect:
        """Draw the type badge."""
        font = QFont()
        font.setPixelSize(self.FONT_SIZE_SMALL)
        font.setBold(True)
        painter.setFont(font)
        
        text = object_type.value.upper()
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(text)
        
        badge_rect = QRect(x, y, text_width + 12, 18)
        
        # Draw badge background
        path = QPainterPath()
        path.addRoundedRect(QRectF(badge_rect), 3, 3)
        painter.fillPath(path, color.darker(150))
        
        # Draw text
        painter.setPen(color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        
        return badge_rect
    
    def _draw_origin_badge(self, painter: QPainter, x: int, y: int, 
                           text: str, color: QColor) -> QRect:
        """Draw the origin badge (REMOTE/LOCAL)."""
        font = QFont()
        font.setPixelSize(self.FONT_SIZE_SMALL - 1)
        font.setBold(True)
        painter.setFont(font)
        
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(text)
        
        badge_rect = QRect(x, y, text_width + 10, 16)
        
        # Draw badge background
        path = QPainterPath()
        path.addRoundedRect(QRectF(badge_rect), 3, 3)
        painter.fillPath(path, color.darker(200))
        
        # Draw border
        painter.setPen(QPen(color, 1))
        painter.drawPath(path)
        
        # Draw text
        painter.setPen(color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        
        return badge_rect
    
    def _draw_name(self, painter: QPainter, x: int, y: int, width: int, info: ObjectInfo):
        """Draw the object name."""
        font = QFont()
        font.setPixelSize(self.FONT_SIZE + 2)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.COLOR_TEXT)
        
        metrics = QFontMetrics(font)
        elided = metrics.elidedText(info.display_name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(x, y + metrics.ascent(), elided)
    
    def _draw_summary(self, painter: QPainter, x: int, y: int, width: int, info: ObjectInfo):
        """Draw the summary text and optional path."""
        font = QFont()
        font.setPixelSize(self.FONT_SIZE)
        painter.setFont(font)
        painter.setPen(self.COLOR_TEXT_DIM)
        
        metrics = QFontMetrics(font)
        elided = metrics.elidedText(info.summary, Qt.TextElideMode.ElideRight, width)
        painter.drawText(x, y + metrics.ascent(), elided)
        
        # Draw path for local items (below summary)
        if info.path and not info.is_remote:
            path_y = y + metrics.height() + 2
            path_font = QFont()
            path_font.setPixelSize(self.FONT_SIZE_SMALL - 1)
            painter.setFont(path_font)
            painter.setPen(self.COLOR_TEXT_MUTED)
            
            path_metrics = QFontMetrics(path_font)
            path_str = str(info.path)
            elided_path = path_metrics.elidedText(path_str, Qt.TextElideMode.ElideMiddle, width)
            painter.drawText(x, path_y + path_metrics.ascent(), elided_path)
    
    def _draw_version(self, painter: QPainter, rect: QRect, info: ObjectInfo):
        """Draw the version indicator."""
        font = QFont()
        font.setPixelSize(self.FONT_SIZE_SMALL)
        painter.setFont(font)
        painter.setPen(self.COLOR_TEXT_MUTED)
        
        painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 
                        f"v{info.version}")
    
    def _draw_status(self, painter: QPainter, rect: QRect, info: ObjectInfo):
        """Draw the status indicator or action button."""
        # Determine status color and text
        if info.is_added:
            color = self.COLOR_ADDED
            text = "Added"
        elif info.is_remote:
            if info.download_status == DownloadStatus.DOWNLOADED:
                color = self.COLOR_ADDED
                text = "Downloaded"
            elif info.download_status == DownloadStatus.DOWNLOADING:
                color = self.COLOR_REMOTE
                text = "..."
            else:
                # Show download action for remote objects
                color = self.COLOR_BORDER  # O3DE blue for clickable
                text = "Download"
        else:
            color = self.COLOR_TEXT_DIM
            text = "Local"
        
        # Draw button background
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 4, 4)
        painter.fillPath(path, color.darker(200))
        
        # Draw border
        painter.setPen(QPen(color, 1))
        painter.drawPath(path)
        
        # Draw text
        font = QFont()
        font.setPixelSize(self.FONT_SIZE_SMALL)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
