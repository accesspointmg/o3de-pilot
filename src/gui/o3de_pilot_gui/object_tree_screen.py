# O3DE Pilot GUI - Object Tree Screen
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Tree view screen for visualizing O3DE object hierarchy.

The root of the tree is o3de_manifest. ALL objects can have:
- Children of any type (objects contained within)
- Dependencies of any type (required objects)
- Remotes of any type (objects available from remote sources)

Plus transitive closures: All Dependencies, All Remotes.

Double-click any child/dependency/remote/overlay to drill down into its
own structure inline — expanding arbitrarily deep through the graph.
"""

import re
from collections import OrderedDict
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QBrush, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QLabel, QMenu, QApplication, QHeaderView,
)

from o3de_cli.core import ObjectType
from o3de_cli.core.resolver import Resolver, ResolvedObject, load_resolved_manifest
from .command_specs import get_context_commands


# Roles for storing object data on tree items
_ROLE_OBJECT_NAME = Qt.ItemDataRole.UserRole
_ROLE_OBJECT_TYPE = Qt.ItemDataRole.UserRole + 1
_ROLE_EXPANDED    = Qt.ItemDataRole.UserRole + 2   # bool: already drilled-down

# Regex to split "name>=1.0.0" or "name>=1.0,<2.0" etc.
_DEP_SPEC_RE = re.compile(r'^([A-Za-z0-9._-]+)(.*)')


def _parse_dep_specifier(spec: str) -> tuple[str, str]:
    """Split 'org.o3de.gem.foo>=1.0.0' -> ('org.o3de.gem.foo', '>=1.0.0')."""
    m = _DEP_SPEC_RE.match(spec.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return spec.strip(), ""


# Colours
_COLORS = {
    "engine":   QColor("#4FC3F7"),   # light blue
    "project":  QColor("#81C784"),   # green
    "gem":      QColor("#FFB74D"),   # orange
    "template": QColor("#CE93D8"),   # purple
    "repo":     QColor("#90A4AE"),   # grey-blue
    "overlay":  QColor("#F06292"),   # pink
    "child":    QColor("#80DEEA"),   # cyan
    "dep":      QColor("#A5D6A7"),   # light green
    "opt_dep":  QColor("#E0E0E0"),   # dim grey
    "peer_dep": QColor("#64B5F6"),   # blue
    "all_dep":  QColor("#B0BEC5"),   # blue-grey (transitive)
    "remote":   QColor("#FFAB91"),   # light coral/orange
    "missing":  QColor("#EF5350"),   # red
    "default":  QColor("#CCCCCC"),
    "manifest": QColor("#FFF176"),   # yellow
}

_TYPE_LABELS = {
    "engine":   "Engines",
    "project":  "Projects",
    "gem":      "Gems",
    "template": "Templates",
    "repo":     "Repos",
    "overlay":  "Overlays",
}

# Consistent type ordering
_TYPE_ORDER = ["engine", "project", "gem", "template", "repo", "overlay", ""]


class ObjectTreeScreen(QWidget):
    """
    Hierarchical tree view of all resolved O3DE objects.

    Layout:
    +----------------------------------------------+
    |  [Search...]                                 |
    +----------------------------------------------+
    |  Name          | Type     | Version | Status |
    |  > o3de_manifest manifest           root     |
    |    > Children (132)                          |
    |      > Engines (1)                           |
    |        > o3de    engine     2.0.0    local    |
    |          > Children (97)                     |
    |          > Dependencies (2)                  |
    |          > Remotes (1)                       |
    |          > All Dependencies (5)              |
    |          > All Remotes (81)                  |
    |      > Gems (115)                            |
    |        ...                                   |
    |    > Remotes (1)                             |
    |      > overlo3de  repo            remote     |
    |        > Children (49)                       |
    |        > Remotes (2)                         |
    +----------------------------------------------+

    Double-click any child / dependency / remote / overlay item to
    expand its own structure inline.
    """

    objectSelected = Signal(str)  # object name
    commandRequested = Signal(dict, object)  # (command_spec, SimpleNamespace|None)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._all_objects: dict[str, ResolvedObject] = {}
        self._resolved_data: dict = {}  # cached manifest data for drill-down
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setStyleSheet("background-color: #1A1A1A; border-bottom: 1px solid #333333;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Object Tree")
        title.setStyleSheet("color: #EEEEEE; font-size: 10.5pt; font-weight: bold;")
        header_layout.addWidget(title)

        self._count_label = QLabel("0 objects")
        self._count_label.setStyleSheet("color: #999999; font-size: 9pt;")
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        # Search box
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter objects...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(260)
        self._search.setStyleSheet("""
            QLineEdit {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)
        self._search.textChanged.connect(self._apply_filter)
        header_layout.addWidget(self._search)

        layout.addWidget(header)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Name", "Type", "Version", "Status"])
        self._tree.setAlternatingRowColors(False)
        self._tree.setAnimated(True)
        self._tree.setIndentation(20)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background-color: #222222;
                color: #CCCCCC;
                border: none;
                font-size: 9pt;
            }
            QTreeWidget::item {
                padding: 3px 0px;
            }
            QTreeWidget::item:selected {
                background-color: #0078D4;
                color: #FFFFFF;
            }
            QTreeWidget::item:hover {
                background-color: #2A2D2E;
            }
            QHeaderView::section {
                background-color: #1A1A1A;
                color: #AAAAAA;
                border: none;
                border-bottom: 1px solid #333333;
                padding: 6px 8px;
                font-weight: bold;
            }
        """)

        # Column sizing
        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.currentItemChanged.connect(self._on_current_changed)
        self._tree.itemDoubleClicked.connect(self._on_double_click)

        layout.addWidget(self._tree)

        self.setStyleSheet("background-color: #222222;")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, resolver: Resolver):
        """Build the tree from a fully-resolved Resolver."""
        self._all_objects = dict(resolver.objects)
        self._tree.clear()

        # Prefer the saved cache (which has remotes/all_remotes/manifest_root)
        try:
            cached = load_resolved_manifest()
            self._resolved_data = cached.get("objects", {})
            manifest_root = cached.get("manifest_root")
        except Exception:
            self._resolved_data = {}
            manifest_root = None

        # Ensure all local objects are in _resolved_data
        for name, obj in resolver.objects.items():
            if name not in self._resolved_data:
                self._resolved_data[name] = {
                    "type": obj.object_type.value,
                    "version": obj.version,
                    "children": [c.name for c in obj.children],
                    "dependencies": [str(d) for d in obj.dependencies],
                    "optional_dependencies": [str(d) for d in obj.optional_dependencies] or None,
                    "peer_dependencies": [str(d) for d in obj.peer_dependencies] or None,
                    "all_dependencies": [
                        {"name": dn, "version": dv}
                        for dn, dv in resolver.dependency_graph.get(name, [])
                    ] or None,
                    "overlays": [o.name for o in obj.overlays],
                }

        self._build_tree(manifest_root)

    def populate_from_cache(self, resolved_data: dict | None = None):
        """Populate tree from the cached resolved manifest (no Resolver needed).

        Args:
            resolved_data: Pre-loaded resolved manifest dict. If *None*,
                loads from disk (may block if re-resolution is needed).
        """
        try:
            data = resolved_data if resolved_data is not None else load_resolved_manifest()
        except Exception:
            return

        self._resolved_data = data.get("objects", {})
        manifest_root = data.get("manifest_root")
        self._tree.clear()
        self._build_tree(manifest_root)

    def clear(self):
        """Clear the tree."""
        self._tree.clear()
        self._all_objects.clear()
        self._resolved_data = {}
        self._count_label.setText("0 objects")

    # ------------------------------------------------------------------
    # Tree-building core
    # ------------------------------------------------------------------

    def _build_tree(self, manifest_root: dict | None):
        """Build the tree from manifest root + resolved data."""
        total = len(self._resolved_data)
        bold_font = QFont()
        bold_font.setBold(True)

        if manifest_root:
            # Single root: o3de_manifest
            root_name = manifest_root.get("name", "o3de_manifest")
            root_item = QTreeWidgetItem(self._tree)
            root_item.setText(0, root_name)
            root_item.setText(1, "manifest")
            root_item.setText(3, "root")
            root_item.setFont(0, bold_font)
            root_item.setForeground(0, QBrush(_COLORS["manifest"]))
            root_item.setData(0, _ROLE_OBJECT_NAME, root_name)

            # Manifest's sub-nodes: Children, All Children, Remotes, All Remotes
            children = manifest_root.get("children", [])
            all_children = manifest_root.get("all_children") or []
            remotes = manifest_root.get("remotes", [])
            all_remotes = manifest_root.get("all_remotes") or []

            if children:
                self._add_children_group(root_item, children)
            if all_children:
                direct_child_names = set(
                    c if isinstance(c, str) else c.get("name", str(c))
                    for c in children
                )
                self._add_all_children_group(root_item, all_children, direct_child_names)
            if remotes:
                self._add_remotes_group(root_item, remotes)
            if all_remotes:
                direct_set = set(remotes) if remotes else set()
                self._add_all_remotes_group(root_item, all_remotes, direct_set)

            root_item.setExpanded(True)
        else:
            # Fallback: group by type (no manifest_root in cache)
            buckets: dict[str, list[tuple[str, dict]]] = {}
            for name, obj_data in self._resolved_data.items():
                t = obj_data.get("type", "gem")
                buckets.setdefault(t, []).append((name, obj_data))

            for type_key in _TYPE_ORDER:
                items = buckets.get(type_key, [])
                if not items:
                    continue
                label = _TYPE_LABELS.get(type_key, type_key.title() + "s")
                cat_item = QTreeWidgetItem(self._tree)
                cat_item.setText(0, f"{label} ({len(items)})")
                cat_item.setFont(0, bold_font)
                cat_item.setForeground(0, QBrush(_COLORS.get(type_key, _COLORS["default"])))
                cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for name, obj_data in sorted(items, key=lambda x: x[0]):
                    self._make_object_leaf(cat_item, name, obj_data)
                cat_item.setExpanded(True)

        self._count_label.setText(f"{total} object{'s' if total != 1 else ''}")

    # ------------------------------------------------------------------
    # Group builders (Children, Dependencies, Remotes, etc.)
    # ------------------------------------------------------------------

    def _add_children_group(self, parent: QTreeWidgetItem, children: list):
        """Add a Children group, categorized by type."""
        group = self._group_item(parent, f"Children ({len(children)})")
        entries = []
        for child in children:
            c_name = child if isinstance(child, str) else child.get("name", str(child))
            entries.append((c_name, {}))
        self._add_typed_entries(group, entries, self._make_child_leaf)

    def _add_deps_group(self, parent: QTreeWidgetItem, deps: list):
        """Add a Dependencies group, categorized by type."""
        group = self._group_item(parent, f"Dependencies ({len(deps)})")
        entries = []
        for dep in deps:
            if isinstance(dep, str):
                d_name, d_ver = _parse_dep_specifier(dep)
            else:
                d_name = dep.get("name", str(dep))
                d_ver = dep.get("version_specifier", dep.get("version", ""))
            entries.append((d_name, {"ver": d_ver}))
        self._add_typed_entries(group, entries, self._make_dep_leaf)

    def _add_remotes_group(self, parent: QTreeWidgetItem, remotes: list):
        """Add a Remotes group, categorized by type."""
        group = self._group_item(parent, f"Remotes ({len(remotes)})")
        entries = []
        for r in remotes:
            r_name = r if isinstance(r, str) else r.get("name", str(r))
            entries.append((r_name, {}))
        self._add_typed_entries(group, entries, self._make_remote_leaf)

    def _add_all_deps_group(self, parent: QTreeWidgetItem, all_deps: list, direct_names: set):
        """Add an All Dependencies group, categorized by type."""
        group = self._group_item(parent, f"All Dependencies ({len(all_deps)})")
        entries = []
        for dep in all_deps:
            if isinstance(dep, dict):
                d_name = dep.get("name", "")
                d_ver = dep.get("version", "")
            else:
                d_name, d_ver = _parse_dep_specifier(str(dep))
            entries.append((d_name, {"ver": d_ver, "direct": d_name in direct_names}))
        self._add_typed_entries(group, entries, self._make_all_dep_leaf)

    def _add_all_children_group(self, parent: QTreeWidgetItem, all_children: list, direct_names: set):
        """Add an All Children group (transitive closure), categorized by type."""
        group = self._group_item(parent, f"All Children ({len(all_children)})")
        entries = []
        for child in all_children:
            if isinstance(child, dict):
                c_name = child.get("name", "")
            else:
                c_name = str(child)
            entries.append((c_name, {"direct": c_name in direct_names}))
        self._add_typed_entries(group, entries, self._make_all_child_leaf)

    def _add_all_remotes_group(self, parent: QTreeWidgetItem, all_remotes: list, direct_set: set):
        """Add an All Remotes group, categorized by type."""
        group = self._group_item(parent, f"All Remotes ({len(all_remotes)})")
        entries = []
        for entry in all_remotes:
            if isinstance(entry, dict):
                r_name = entry.get("name", "")
            else:
                r_name = str(entry)
            entries.append((r_name, {"direct": r_name in direct_set}))
        self._add_typed_entries(group, entries, self._make_all_remote_leaf)

    def _add_sub_nodes(self, item: QTreeWidgetItem, obj_data: dict):
        """
        Add all relationship groups (Children, Dependencies, Remotes, etc.)
        from dict data. This is the uniform handler for ALL objects.
        """
        children = obj_data.get("children", [])
        deps = obj_data.get("dependencies", [])
        remotes = obj_data.get("remotes", [])
        opt_deps = obj_data.get("optional_dependencies") or []
        peer_deps = obj_data.get("peer_dependencies") or []
        all_deps = obj_data.get("all_dependencies") or []
        all_remotes = obj_data.get("all_remotes") or []
        overlays = obj_data.get("overlays", [])

        all_children = obj_data.get("all_children") or []

        # Children
        if children:
            self._add_children_group(item, children)

        # All Children (transitive)
        if all_children:
            direct_child_names = set(
                c if isinstance(c, str) else c.get("name", str(c))
                for c in children
            )
            self._add_all_children_group(item, all_children, direct_child_names)

        # Dependencies
        if deps:
            self._add_deps_group(item, deps)

        # Remotes
        if remotes:
            self._add_remotes_group(item, remotes)

        # Optional dependencies
        if opt_deps:
            group = self._group_item(item, f"Optional Deps ({len(opt_deps)})")
            for dep in opt_deps:
                if isinstance(dep, str):
                    d_name, d_ver = _parse_dep_specifier(dep)
                else:
                    d_name = dep.get("name", str(dep))
                    d_ver = dep.get("version_specifier", dep.get("version", ""))
                self._dep_item(group, d_name, "optional", d_ver, _COLORS["opt_dep"])

        # Peer dependencies
        if peer_deps:
            group = self._group_item(item, f"Peer Deps ({len(peer_deps)})")
            for dep in peer_deps:
                if isinstance(dep, str):
                    d_name, d_ver = _parse_dep_specifier(dep)
                else:
                    d_name = dep.get("name", str(dep))
                    d_ver = dep.get("version_specifier", dep.get("version", ""))
                self._dep_item(group, d_name, "peer", d_ver, _COLORS["peer_dep"])

        # All Dependencies (transitive)
        if all_deps:
            direct_names = set()
            for dep in deps:
                if isinstance(dep, str):
                    dn, _ = _parse_dep_specifier(dep)
                else:
                    dn = dep.get("name", "")
                direct_names.add(dn)
            self._add_all_deps_group(item, all_deps, direct_names)

        # All Remotes (transitive)
        if all_remotes:
            direct_set = set(remotes) if remotes else set()
            self._add_all_remotes_group(item, all_remotes, direct_set)

        # Overlays
        if overlays:
            group = self._group_item(item, f"Overlays ({len(overlays)})")
            for ov in overlays:
                o_name = ov if isinstance(ov, str) else ov.get("name", str(ov))
                self._dep_item(group, o_name, "overlay", "", _COLORS["overlay"])

        # Deprecation styling
        dep_info = obj_data.get("deprecation", {})
        if dep_info and dep_info.get("deprecated", False):
            font = item.font(0)
            font.setStrikeOut(True)
            item.setFont(0, font)
            item.setText(3, "deprecated")
            item.setForeground(3, QBrush(_COLORS["missing"]))

    # ------------------------------------------------------------------
    # Type bucketing
    # ------------------------------------------------------------------

    def _type_for_name(self, name: str) -> str:
        """Look up an object's type from resolved data. Returns '' if unknown."""
        d = self._resolved_data.get(name, {})
        return d.get("type", "")

    def _bucket_by_type(
        self, names_data: list[tuple[str, dict]]
    ) -> dict[str, list[tuple[str, dict]]]:
        """Group (name, extra_data) tuples by resolved object type."""
        buckets: dict[str, list[tuple[str, dict]]] = {}
        for name, extra in names_data:
            t = self._type_for_name(name)
            buckets.setdefault(t, []).append((name, extra))
        result: dict[str, list[tuple[str, dict]]] = OrderedDict()
        for t in _TYPE_ORDER:
            if t in buckets:
                result[t] = sorted(buckets.pop(t), key=lambda x: x[0])
        for t in sorted(buckets):
            result[t] = sorted(buckets[t], key=lambda x: x[0])
        return result

    def _add_typed_entries(
        self,
        group: QTreeWidgetItem,
        entries: list[tuple[str, dict]],
        make_fn,
    ):
        """Add entries to a group, categorizing by type when multiple types."""
        buckets = self._bucket_by_type(entries)
        for type_key, items in buckets.items():
            label = _TYPE_LABELS.get(type_key, type_key.title() + "s") if type_key else "Other"
            color = _COLORS.get(type_key, _COLORS["default"])
            sub = self._group_item(group, f"{label} ({len(items)})")
            sub.setForeground(0, QBrush(color))
            for name, extra in items:
                make_fn(sub, name, extra)

    # ------------------------------------------------------------------
    # Leaf item factories
    # ------------------------------------------------------------------

    def _make_object_leaf(self, parent: QTreeWidgetItem, name: str, obj_data: dict):
        """Create a tree item from resolved data with all sub-nodes."""
        obj_type = obj_data.get("type", "")
        color = _COLORS.get(obj_type, _COLORS["default"])
        item = QTreeWidgetItem(parent)
        item.setText(0, name)
        item.setText(1, obj_type)
        item.setText(2, obj_data.get("version", ""))
        item.setText(3, obj_data.get("status", "local"))
        item.setForeground(0, QBrush(color))
        item.setData(0, _ROLE_OBJECT_NAME, name)
        item.setData(0, _ROLE_OBJECT_TYPE, obj_type)
        self._add_sub_nodes(item, obj_data)
        item.setData(0, _ROLE_EXPANDED, True)
        return item

    def _make_child_leaf(self, parent: QTreeWidgetItem, name: str, extra: dict):
        """Create a child leaf item (drillable via double-click)."""
        c_data = self._resolved_data.get(name, {})
        c_type = c_data.get("type", "")
        c_ver = c_data.get("version", "")
        color = _COLORS.get(c_type, _COLORS["child"])
        status = c_data.get("status", "resolved" if c_data else "")
        ci = self._dep_item(parent, name, c_type, c_ver, color)
        if status:
            ci.setText(3, status)

    def _make_dep_leaf(self, parent: QTreeWidgetItem, name: str, extra: dict):
        """Create a direct dependency leaf item (drillable via double-click)."""
        d_ver = extra.get("ver", "")
        resolved = name in self._resolved_data
        d_type = self._type_for_name(name)
        color = _COLORS.get(d_type, _COLORS["dep"]) if resolved else _COLORS["missing"]
        status = "resolved" if resolved else "missing"
        di = self._dep_item(parent, name, d_type or "dep", d_ver, color)
        di.setText(3, status)
        if not resolved:
            di.setForeground(3, QBrush(_COLORS["missing"]))

    def _make_remote_leaf(self, parent: QTreeWidgetItem, name: str, extra: dict):
        """Create a remote leaf item (drillable — works like a child)."""
        r_data = self._resolved_data.get(name, {})
        r_type = r_data.get("type", "repo")
        r_ver = r_data.get("version", "")
        color = _COLORS.get(r_type, _COLORS["remote"])
        status = r_data.get("status", "remote")
        ri = self._dep_item(parent, name, r_type, r_ver, color)
        ri.setText(3, status)
        dm = r_data.get("display_metadata") or {}
        if dm.get("summary"):
            ri.setToolTip(0, dm["summary"])

    def _make_all_dep_leaf(self, parent: QTreeWidgetItem, name: str, extra: dict):
        """Create a transitive dependency leaf item."""
        d_ver = extra.get("ver", "")
        is_direct = extra.get("direct", False)
        d_type = self._type_for_name(name)
        color = _COLORS.get(d_type, _COLORS["dep"]) if is_direct else _COLORS.get(d_type, _COLORS["all_dep"])
        label = "direct" if is_direct else "transitive"
        di = self._dep_item(parent, name, d_type or label, d_ver, color)
        di.setText(3, "resolved")

    def _make_all_child_leaf(self, parent: QTreeWidgetItem, name: str, extra: dict):
        """Create a transitive child leaf item (direct/transitive label)."""
        c_data = self._resolved_data.get(name, {})
        c_type = c_data.get("type", self._type_for_name(name) or "")
        c_ver = c_data.get("version", "")
        is_direct = extra.get("direct", False)
        color = _COLORS.get(c_type, _COLORS["child"])
        status = "direct" if is_direct else "transitive"
        ci = self._dep_item(parent, name, c_type, c_ver, color)
        ci.setText(3, status)

    def _make_all_remote_leaf(self, parent: QTreeWidgetItem, name: str, extra: dict):
        """Create a transitive remote leaf item."""
        r_data = self._resolved_data.get(name, {})
        r_type = r_data.get("type", self._type_for_name(name) or "repo")
        is_direct = extra.get("direct", False)
        color = _COLORS.get(r_type, _COLORS["remote"])
        status = "direct" if is_direct else "transitive"
        ri = self._dep_item(parent, name, r_type, "", color)
        ri.setText(3, status)

    def _dep_item(
        self,
        parent: QTreeWidgetItem,
        name: str,
        type_label: str,
        version: str,
        color: QColor,
    ) -> QTreeWidgetItem:
        """Create a dependency/child/remote/overlay sub-item with _ROLE_OBJECT_NAME set."""
        di = QTreeWidgetItem(parent)
        di.setText(0, name)
        di.setText(1, type_label)
        di.setText(2, version)
        di.setForeground(0, QBrush(color))
        di.setData(0, _ROLE_OBJECT_NAME, name)
        return di

    def _group_item(self, parent: QTreeWidgetItem, label: str) -> QTreeWidgetItem:
        """Create a non-selectable group header item."""
        item = QTreeWidgetItem(parent)
        item.setText(0, label)
        item.setForeground(0, QBrush(QColor("#888888")))
        font = item.font(0)
        font.setItalic(True)
        item.setFont(0, font)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        return item

    # ------------------------------------------------------------------
    # Double-click drill-down
    # ------------------------------------------------------------------

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        """
        Double-click a child / dependency / remote / overlay to expand
        its own structure inline (children, deps, remotes, all-deps, etc.).
        """
        if item.data(0, _ROLE_EXPANDED):
            return

        name = item.data(0, _ROLE_OBJECT_NAME)
        if not name:
            return

        obj_data = self._resolved_data.get(name)
        if not obj_data:
            placeholder = QTreeWidgetItem(item)
            placeholder.setText(0, "(not resolved)")
            placeholder.setForeground(0, QBrush(QColor("#666666")))
            font = placeholder.font(0)
            font.setItalic(True)
            placeholder.setFont(0, font)
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setData(0, _ROLE_EXPANDED, True)
            item.setExpanded(True)
            return

        self._add_sub_nodes(item, obj_data)
        item.setData(0, _ROLE_EXPANDED, True)
        item.setExpanded(True)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str):
        """Show/hide tree items based on search text."""
        text = text.lower().strip()
        root = self._tree.invisibleRootItem()

        def _filter_item(item: QTreeWidgetItem) -> bool:
            """Returns True if this item or any descendant matches."""
            name_match = not text or text in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                if _filter_item(item.child(i)):
                    child_match = True
            visible = name_match or child_match
            item.setHidden(not visible)
            return visible

        for i in range(root.childCount()):
            _filter_item(root.child(i))

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #EEEEEE;
                border: 1px solid #444444;
            }
            QMenu::item:selected {
                background-color: #0078D4;
            }
        """)

        name = item.data(0, _ROLE_OBJECT_NAME) or item.text(0)
        copy_action = QAction(f"Copy \"{name}\"", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(name))
        menu.addAction(copy_action)

        obj_name = item.data(0, _ROLE_OBJECT_NAME)
        if obj_name and not item.data(0, _ROLE_EXPANDED) and obj_name in self._resolved_data:
            drill_action = QAction(f"Expand \"{obj_name}\"", self)
            drill_action.triggered.connect(lambda: self._on_double_click(item, 0))
            menu.addAction(drill_action)

        # ── Type-aware CLI commands ───────────────────────────────
        obj_type = item.data(0, _ROLE_OBJECT_TYPE) or ""
        specs = get_context_commands(obj_type) if obj_type else []
        if specs:
            menu.addSeparator()
            for spec in specs:
                if spec is None:
                    menu.addSeparator()
                else:
                    act = menu.addAction(spec["title"])
                    act.setToolTip(spec.get("description", ""))
                    # Build a lightweight object-like namespace for pre-fill
                    from types import SimpleNamespace
                    sel_obj = SimpleNamespace(
                        name=obj_name or name,
                        path="",
                        object_type=obj_type,
                    )
                    act.triggered.connect(
                        lambda _c=False, s=spec, o=sel_obj: self.commandRequested.emit(s, o)
                    )

        menu.addSeparator()

        expand_action = QAction("Expand All", self)
        expand_action.triggered.connect(self._tree.expandAll)
        menu.addAction(expand_action)

        collapse_action = QAction("Collapse All", self)
        collapse_action.triggered.connect(self._tree.collapseAll)
        menu.addAction(collapse_action)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_current_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem):
        if current:
            name = current.data(0, _ROLE_OBJECT_NAME)
            if name:
                self.objectSelected.emit(name)
