# O3DE Pilot - Schema Upgrade
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Schema Upgrade Module.

Handles migration between schema versions following O3DE's upgrade_schema.py:
- Version 0 (legacy): No $schemaVersion, uses {type}_name fields
- Version 1.0.0: Has $schemaVersion, still uses {type}_name fields  
- Version 2.0.0: Formal JSON schema with nested object properties (e.g., gem.name)

The upgrade path is always: 0 → 1.0.0 → 2.0.0 (incremental)
"""

from pathlib import Path
from typing import Optional, Any, Callable
import json
import logging
import shutil
import re
from datetime import datetime, timezone

logger = logging.getLogger("o3de_pilot.upgrade")


class UpgradeError(Exception):
    """Error during schema upgrade."""
    pass


# Schema version patterns
SCHEMA_URL_PATTERN = re.compile(r"https?://[^/]+/o3de-(\w+)-(\d+\.\d+\.\d+)\.json")


def is_reverse_domain_format(name: str) -> bool:
    """Check if a name is in reverse domain format (e.g., org.o3de.gem.foo)."""
    if not name or name.count('.') < 2:
        return False
    
    # Common TLDs that appear as first segment in reverse domain
    tlds = {'org', 'com', 'net', 'edu', 'gov', 'io', 'me'}
    first_segment = name.split('.')[0]
    return first_segment in tlds and name.islower()


def is_url(s: str) -> bool:
    """Check if a string is a URL."""
    return s.startswith(('http://', 'https://', 'ftp://', 'ftps://'))


def get_canonical_tag(tag: str) -> Optional[str]:
    """Get canonical tag name or None if invalid."""
    canonical_mapping = {
        "engine": "Engine",
        "project": "Project",
        "gem": "Gem",
        "template": "Template",
        "repo": "Repo",
        "overlay": "Overlay"
    }
    return canonical_mapping.get(tag.lower())


def get_schema_version(data: dict) -> tuple[str, str]:
    """
    Get schema version from object data.
    
    Returns:
        Tuple of (object_type, version_string)
        Version is "0" for legacy (no $schemaVersion), or the actual version
    """
    # Check for $schemaVersion first (O3DE standard)
    schema_version = data.get("$schemaVersion", "")
    schema_url = data.get("$schema", "")
    
    # If no $schemaVersion, this is version 0
    if not schema_version:
        # Detect type from version 0 fields
        if "o3de_manifest_name" in data:
            return ("manifest", "0")
        elif "engine_name" in data:
            return ("engine", "0")
        elif "project_name" in data:
            return ("project", "0")
        elif "gem_name" in data:
            return ("gem", "0")
        elif "template_name" in data:
            return ("template", "0")
        elif "repo_name" in data:
            return ("repo", "0")
        elif "restricted_name" in data:
            return ("restricted", "0")
        # Check for 2.0.0 format nested objects
        elif "engine" in data and isinstance(data.get("engine"), dict):
            return ("engine", "0")
        elif "project" in data and isinstance(data.get("project"), dict):
            return ("project", "0")
        elif "gem" in data and isinstance(data.get("gem"), dict):
            return ("gem", "0")
        elif "template" in data and isinstance(data.get("template"), dict):
            return ("template", "0")
        elif "repo" in data and isinstance(data.get("repo"), dict):
            return ("repo", "0")
        elif "o3de_manifest" in data and isinstance(data.get("o3de_manifest"), dict):
            return ("manifest", "0")
        else:
            return ("unknown", "0")
    
    # Has $schemaVersion - determine type
    version = schema_version
    
    # Try to get type from schema URL
    if schema_url:
        match = SCHEMA_URL_PATTERN.match(schema_url)
        if match:
            return (match.group(1), match.group(2))
        
        # Fallback: parse from URL
        for obj_type in ["manifest", "engine", "project", "gem", "template", "repo", "overlay"]:
            if obj_type in schema_url:
                return (obj_type, version)
    
    # Detect type from data fields
    if "o3de_manifest_name" in data or "o3de_manifest" in data:
        return ("manifest", version)
    elif "engine_name" in data or "engine" in data and isinstance(data.get("engine"), dict):
        return ("engine", version)  
    elif "project_name" in data or "project" in data and isinstance(data.get("project"), dict):
        return ("project", version)
    elif "gem_name" in data or "gem" in data and isinstance(data.get("gem"), dict):
        return ("gem", version)
    elif "template_name" in data or "template" in data and isinstance(data.get("template"), dict):
        return ("template", version)
    elif "repo_name" in data or "repo" in data and isinstance(data.get("repo"), dict):
        return ("repo", version)
    elif "restricted_name" in data or "restricted" in data and isinstance(data.get("restricted"), dict):
        return ("restricted", version)
    elif "overlay" in data and isinstance(data.get("overlay"), dict):
        return ("overlay", version)
    
    return ("unknown", version)


def needs_upgrade(data: dict, target_version: str = "2.0.0") -> bool:
    """Check if data needs upgrade to target version."""
    _, current_version = get_schema_version(data)
    
    if current_version == "0":
        return True
    
    from packaging.version import Version
    try:
        return Version(current_version) < Version(target_version)
    except Exception:
        return True


# ============================================================================
# Version 0 → 1.0.0 Upgrade  
# ============================================================================

def upgrade_0_to_1(data: dict, object_type: str) -> dict:
    """
    Upgrade from version 0 (legacy) to version 1.0.0.
    
    Key changes:
    - Add $schemaVersion: "1.0.0"
    - Keep {type}_name fields (engine_name, gem_name, etc.)
    - Normalize url/uri fields to {type}_uri
    - Add version, display_name, summary, last_updated defaults
    """
    output = {"$schemaVersion": "1.0.0"}
    
    if object_type == "manifest":
        output["o3de_manifest_name"] = data.get("o3de_manifest_name", "")
        output["default_engines_folder"] = data.get("default_engines_folder", "")
        output["default_projects_folder"] = data.get("default_projects_folder", "")
        output["default_gems_folder"] = data.get("default_gems_folder", "")
        output["default_templates_folder"] = data.get("default_templates_folder", "")
        output["default_restricted_folder"] = data.get("default_restricted_folder", "")
        output["default_repos_folder"] = data.get("default_repos_folder", "")
        output["default_third_party_folder"] = data.get("default_third_party_folder", "")
        
    elif object_type == "engine":
        output["engine_name"] = data.get("engine_name", "")
        # Normalize URI fields
        output["engine_uri"] = data.get("engine_uri", data.get("engine_url", 
            data.get("url", data.get("uri", ""))))
        output["engine_type"] = data.get("engine_type", data.get("type", ""))
        if "O3DEVersion" in data:
            output["O3DEVersion"] = data["O3DEVersion"]
        if "O3DEBuildNumber" in data:
            output["O3DEBuildNumber"] = data["O3DEBuildNumber"]
            
    elif object_type == "project":
        output["project_name"] = data.get("project_name", "")
        output["project_uri"] = data.get("project_uri", data.get("project_url",
            data.get("url", data.get("uri", ""))))
        output["project_type"] = data.get("project_type", data.get("type", ""))
        if "project_id" in data:
            output["project_id"] = data["project_id"]
        if "product_name" in data:
            output["product_name"] = data["product_name"]
        if "executable_name" in data:
            output["executable_name"] = data["executable_name"]
        if "engine" in data:
            output["engine"] = data["engine"]
            
    elif object_type == "gem":
        output["gem_name"] = data.get("gem_name", "")
        output["gem_uri"] = data.get("gem_uri", data.get("gem_url",
            data.get("url", data.get("uri", ""))))
        output["gem_type"] = data.get("gem_type", data.get("type", ""))
            
    elif object_type == "template":
        output["template_name"] = data.get("template_name", "")
        output["template_uri"] = data.get("template_uri", data.get("template_url",
            data.get("url", data.get("uri", ""))))
        output["template_type"] = data.get("template_type", data.get("type", ""))
            
    elif object_type == "repo":
        output["repo_name"] = data.get("repo_name", "")
        output["repo_uri"] = data.get("repo_uri", data.get("repo_url",
            data.get("url", data.get("uri", ""))))
        output["repo_type"] = data.get("repo_type", data.get("type", ""))
    
    # Note: "restricted" type has no upgrade path - handled in upgrade_to_latest
    
    # Common fields for non-manifest objects
    if object_type != "manifest":
        output["version"] = data.get("version", "0.0.0")
        output["display_name"] = data.get("display_name", data.get("name", ""))
        output["summary"] = data.get("summary", data.get("description", 
            data.get("display_name", data.get("name", ""))))
        
        if "last_updated" in data:
            output["last_updated"] = data["last_updated"]
        else:
            output["last_updated"] = datetime.now(timezone.utc).isoformat()
            
        # Origin fields
        if "origin" in data:
            output["origin"] = data["origin"]
        if "origin_name" in data:
            output["origin_name"] = data["origin_name"]
        if "origin_url" in data or "origin_uri" in data:
            output["origin_url"] = data.get("origin_url", data.get("origin_uri", ""))
            
        # Copyright fields
        if "copyright" in data:
            output["copyright"] = data["copyright"]
        if "copyright_text" in data:
            output["copyright_text"] = data["copyright_text"]
        if "copyright_year" in data:
            output["copyright_year"] = data["copyright_year"]
            
        # Tags
        if "canonical_tags" in data:
            output["canonical_tags"] = data["canonical_tags"]
        if "user_tags" in data:
            output["user_tags"] = data["user_tags"]
            
        # Icon and documentation
        if "icon_path" in data:
            output["icon_path"] = data["icon_path"]
        if "icon_url" in data or "icon_uri" in data:
            output["icon_url"] = data.get("icon_url", data.get("icon_uri", ""))
        if "documentation_path" in data:
            output["documentation_path"] = data["documentation_path"]
        if "documentation_url" in data or "documentation_uri" in data:
            output["documentation_url"] = data.get("documentation_url", 
                data.get("documentation_uri", ""))
            
        # Dependencies and requirements
        if "dependencies" in data:
            output["dependencies"] = data["dependencies"]
        if "requirements" in data:
            output["requirements"] = data["requirements"]
        if "compatible_engines" in data:
            output["compatible_engines"] = data["compatible_engines"]
        if "engine_api_dependencies" in data:
            output["engine_api_dependencies"] = data["engine_api_dependencies"]
            
        # Build
        if "api_versions" in data:
            output["api_versions"] = data["api_versions"]
        if "file_version" in data:
            output["file_version"] = data["file_version"]
        if "build" in data:
            output["build"] = data["build"]
        if "modules" in data:
            output["modules"] = data["modules"]
        if "gem_names" in data:
            output["gem_names"] = data["gem_names"]
    
    # Collection fields (for all types)
    for key in ["engines", "projects", "gems", "templates", "repos", "restricteds",
                "engines_path", "external_subdirectories", "restricted"]:
        if key in data:
            output[key] = data[key]
    
    # Template specific
    if "copyFiles" in data:
        output["copyFiles"] = data["copyFiles"]
    if "createDirectories" in data:
        output["createDirectories"] = data["createDirectories"]
        
    # Source control and downloads
    if "source_control_uri" in data:
        output["source_control_uri"] = data["source_control_uri"]
    if "source_control_path" in data:
        output["source_control_path"] = data["source_control_path"]
    if "source_control_branch" in data:
        output["source_control_branch"] = data["source_control_branch"]
    if "source_control_tag" in data:
        output["source_control_tag"] = data["source_control_tag"]
    if "download_source_uri" in data:
        output["download_source_uri"] = data["download_source_uri"]
    if "versions_data" in data:
        output["versions_data"] = data["versions_data"]
    if "downloads" in data:
        output["downloads"] = data["downloads"]
    if "source_control" in data:
        output["source_control"] = data["source_control"]
    if "releases" in data:
        output["releases"] = data["releases"]
    if "platforms" in data:
        output["platforms"] = data["platforms"]
    if "sha256" in data:
        output["sha256"] = data["sha256"]
    if "additional_info" in data:
        output["additional_info"] = data["additional_info"]
    
    return output


# ============================================================================
# Version 1.0.0 → 2.0.0 Upgrade
# ============================================================================

SCHEMA_HOSTS = {
    "2.0.0": "https://canonical.o3de.org",
}


def upgrade_1_to_2(data: dict, object_type: str) -> dict:
    """
    Upgrade from version 1.0.0 to version 2.0.0.
    
    Key changes:
    - Nest object properties under type key (gem.name, gem.version, etc.)
    - Convert names to reverse-domain format (org.o3de.gem.mygem)
    - Split collections into children (local) and remote (URLs)
    - Create structured sub-objects: origin, licenses, tags, icon, documentation
    - Restructure source_control and download fields
    """
    host = SCHEMA_HOSTS.get("2.0.0", "https://canonical.o3de.org")
    output = {
        "$schemaVersion": "2.0.0",
        "$schema": f"{host}/o3de-{object_type}-2.0.0.json"
    }
    
    # Determine default reversed domain
    reversed_domain = "org.o3de"
    is_o3de = False
    
    # Check if this is an O3DE official object
    name_field = f"{object_type}_name"
    if name_field in data:
        if "o3de" in data[name_field].lower():
            is_o3de = True
    if "origin" in data:
        if isinstance(data["origin"], str) and "o3de.org" in data["origin"].lower():
            is_o3de = True
        elif isinstance(data["origin"], dict):
            if "o3de.org" in data["origin"].get("name", "").lower():
                is_o3de = True
            if "o3de.org" in data["origin"].get("uri", "").lower():
                is_o3de = True
    
    if object_type == "manifest":
        output = _upgrade_manifest_1_to_2(data, output, reversed_domain)
    elif object_type == "engine":
        output = _upgrade_engine_1_to_2(data, output, reversed_domain, is_o3de)
    elif object_type == "project":
        output = _upgrade_project_1_to_2(data, output, reversed_domain, is_o3de)
    elif object_type == "gem":
        output = _upgrade_gem_1_to_2(data, output, reversed_domain, is_o3de)
    elif object_type == "template":
        output = _upgrade_template_1_to_2(data, output, reversed_domain, is_o3de)
    elif object_type == "repo":
        output = _upgrade_repo_1_to_2(data, output, reversed_domain, is_o3de)
    elif object_type == "overlay":
        output = _upgrade_overlay_1_to_2(data, output, reversed_domain, is_o3de)
    elif object_type == "restricted":
        # Restricted objects are not upgraded to 2.0.0 - they are a legacy concept
        # with no equivalent in the new schema. Return None to indicate skip.
        return None
    
    return output


def _make_reverse_domain_name(name: str, obj_type: str, reversed_domain: str = "org.o3de") -> str:
    """Convert a simple name to reverse domain format."""
    if is_reverse_domain_format(name):
        return name.lower()
    return f"{reversed_domain}.{obj_type}.{name}".lower()


def _get_copyright_year(data: dict) -> int | None:
    """Get copyright year as integer, or None if not present/valid."""
    year = data.get("copyright_year")
    if year is None or year == "":
        return None
    try:
        return int(year)
    except (ValueError, TypeError):
        return None


def _split_local_remote(items: list) -> tuple[list, list]:
    """Split a list of paths/URLs into local and remote items."""
    local = []
    remote = []
    for item in items:
        if isinstance(item, str) and is_url(item):
            remote.append(item)
        else:
            local.append(item)
    return local, remote


def _add_origin_and_licenses(output: dict, data: dict, is_o3de: bool) -> dict:
    """Add origin and licenses to output."""
    # Origin
    origin = {}
    if "origin" in data:
        if isinstance(data["origin"], str):
            origin["name"] = data["origin"]
        else:
            origin = data["origin"].copy()
    elif "origin_name" in data:
        origin["name"] = data["origin_name"]
        
    if "origin_url" in data:
        origin["uri"] = data["origin_url"]
    elif "origin_uri" in data:
        origin["uri"] = data["origin_uri"]
    
    if is_o3de and not origin:
        origin = {
            "name": "The Linux Foundation",
            "uri": "https://www.linuxfoundation.org"
        }
    elif not origin.get("name"):
        origin["name"] = "Unknown Origin/Author/Owner"
    
    output["origin"] = origin
    
    # Licenses
    if "license" in data:
        output["licenses"] = [{
            "license_identifier": data.get("license", ""),
            "uri": data.get("license_url", data.get("license_uri", "")),
            "display_name": data.get("license", "").replace("-", " ").replace("_", " "),
            "relative_path": data.get("license_path", "")
        }]
    elif is_o3de:
        output["licenses"] = [
            {
                "license_identifier": "Apache-2.0",
                "uri": "https://spdx.org/licenses/Apache-2.0.html",
                "display_name": "Apache 2.0",
                "relative_path": "LICENSE_APACHE2.TXT"
            },
            {
                "license_identifier": "MIT",
                "uri": "https://spdx.org/licenses/MIT.html",
                "display_name": "MIT",
                "relative_path": "LICENSE_MIT.TXT"
            }
        ]
    else:
        output["licenses"] = [{
            "license_identifier": "Unknown",
            "display_name": "Unknown"
        }]
    
    return output


def _add_tags(output: dict, data: dict, obj_type: str, new_name: str) -> dict:
    """Add tags structure to output.
    
    Schema 2.0.0 uses canonical_tags and user_tags as top-level arrays.
    """
    canonical_tags = []
    user_tags = []
    
    if "canonical_tags" in data:
        for tag in data["canonical_tags"]:
            canonical = get_canonical_tag(tag)
            if canonical:
                canonical_tags.append(canonical)
    
    if "user_tags" in data:
        user_tags = data["user_tags"].copy()
    
    # Ensure the object type is in canonical tags
    type_tag = get_canonical_tag(obj_type)
    if type_tag and type_tag not in canonical_tags:
        canonical_tags.append(type_tag)
    
    # Remove duplicates
    output["canonical_tags"] = list(set(canonical_tags))
    output["user_tags"] = list(set(user_tags))
    return output


def _add_icon_and_docs(output: dict, data: dict) -> dict:
    """Add icon and documentation to output."""
    output["icon"] = {
        "relative_path": data.get("icon_path", ""),
        "uri": data.get("icon_url", data.get("icon_uri", ""))
    }
    output["documentation"] = {
        "relative_path": data.get("documentation_path", ""),
        "uri": data.get("documentation_url", data.get("documentation_uri", ""))
    }
    return output


def _add_children_and_remote(output: dict, data: dict) -> dict:
    """Split collections into children (local) and remote (URLs)."""
    children = {
        "engines": [],
        "projects": [],
        "gems": [],
        "templates": [],
        "repos": [],
        "overlays": []
    }
    remote = {
        "engines": [],
        "projects": [],
        "gems": [],
        "templates": [],
        "repos": [],
        "overlays": []
    }
    
    for key in ["engines", "projects", "gems", "templates", "repos"]:
        if key in data:
            local, rem = _split_local_remote(data[key])
            if local:
                # Ensure paths end with proper JSON file
                json_file = key.rstrip("s") + ".json"
                children[key] = [
                    p if p.endswith(".json") else f"{p.rstrip('/\\')}/{json_file}"
                    for p in local
                ]
            if rem:
                remote[key] = rem
    
    # Note: restricted/restricteds are NOT converted to overlays
    # They are a legacy concept with no upgrade path to 2.0.0
    
    # Handle external_subdirectories (assume gems)
    if "external_subdirectories" in data:
        local, rem = _split_local_remote(data["external_subdirectories"])
        for p in local:
            path = p if p.endswith(".json") else f"{p.rstrip('/\\')}/gem.json"
            if path not in children["gems"]:
                children["gems"].append(path)
        remote["gems"].extend(rem)
    
    output["children"] = children
    output["remote"] = remote
    return output


def _add_source_control(output: dict, data: dict) -> dict:
    """Add structured source_control to output."""
    if any(k in data for k in ["source_control_uri", "source_control_path", 
                               "source_control_branch", "source_control_tag"]):
        sc = {}
        if "source_control_uri" in data:
            uri = data["source_control_uri"]
            sc["git"] = uri if uri.endswith(".git") else f"{uri}.git"
        if "source_control_path" in data:
            sc["relative_path"] = data["source_control_path"]
        if "source_control_branch" in data:
            sc["branch"] = data["source_control_branch"]
        if "source_control_tag" in data:
            sc["tag"] = data["source_control_tag"]
        output["source_control"] = sc
    elif "source_control" in data:
        output["source_control"] = data["source_control"]
    return output


def _add_download(output: dict, data: dict) -> dict:
    """Add structured downloads to output."""
    download_keys = ["download_source_uri", "download_lfs_uri", "download_targz_uri",
                     "download_lfs_targz_uri"]
    
    if any(k in data for k in download_keys):
        # Schema 2.0.0 uses 'downloads' array with 'source' and 'lfs' properties
        download_zip = {}
        download_targz = {}
        if "download_source_uri" in data:
            uri = data["download_source_uri"]
            download_zip["source"] = uri if uri.endswith(".zip") else f"{uri}.zip"
        if "download_lfs_uri" in data:
            uri = data["download_lfs_uri"]
            download_zip["lfs"] = uri if uri.endswith(".zip") else f"{uri}.zip"
        if "download_targz_uri" in data:
            uri = data["download_targz_uri"]
            download_targz["source"] = uri if uri.endswith(".tar.gz") else f"{uri}.tar.gz"
        if "download_lfs_targz_uri" in data:
            uri = data["download_lfs_targz_uri"]
            download_targz["lfs"] = uri if uri.endswith(".tar.gz") else f"{uri}.tar.gz"
        downloads = []
        if download_zip:
            downloads.append(download_zip)
        if download_targz:
            downloads.append(download_targz)
        if downloads:
            output["downloads"] = downloads
    elif "downloads" in data:
        output["downloads"] = data["downloads"]
    return output


def _add_dependent_gems(output: dict, data: dict) -> dict:
    """Convert gem_names and dependencies to dependent.gems with version specifiers."""
    gems = []
    
    for key in ["gem_names", "dependencies"]:
        if key in data:
            deps = data[key]
            if isinstance(deps, list):
                for gem_name in deps:
                    # If already has version specifier or reverse domain, keep as-is
                    if ">=" in gem_name or "<=" in gem_name or "==" in gem_name:
                        gems.append(gem_name)
                    elif is_reverse_domain_format(gem_name):
                        gems.append(gem_name)
                    else:
                        # Convert to reverse domain with any version
                        gems.append(f"org.o3de.gem.{gem_name}>=0.0.0".lower())
    
    if gems:
        output["dependent"] = {"gems": gems}
    else:
        output["dependent"] = {"gems": []}
    
    return output


def _add_releases(output: dict, data: dict) -> dict:
    """Add releases to output."""
    if "releases" in data:
        output["releases"] = data["releases"]
    elif "versions_data" in data:
        releases = []
        for item in data["versions_data"]:
            release = {}
            if "version" in item:
                release["name"] = item["version"]
            
            # Download info - Schema 2.0.0 uses 'source' property
            downloads = []
            download_zip = {}
            download_targz = {}
            if "download_source_uri" in item:
                uri = item["download_source_uri"]
                download_zip["source"] = uri if uri.endswith(".zip") else f"{uri}.zip"
            if "download_lfs_uri" in item:
                uri = item["download_lfs_uri"]
                download_zip["lfs"] = uri if uri.endswith(".zip") else f"{uri}.zip"
            if "download_targz_uri" in item:
                uri = item["download_targz_uri"]
                download_targz["source"] = uri if uri.endswith(".tar.gz") else f"{uri}.tar.gz"
            if "download_lfs_targz_uri" in item:
                uri = item["download_lfs_targz_uri"]
                download_targz["lfs"] = uri if uri.endswith(".tar.gz") else f"{uri}.tar.gz"
            if download_zip:
                downloads.append(download_zip)
            if download_targz:
                downloads.append(download_targz)
            if downloads:
                release["downloads"] = downloads
            
            # Source control - Schema 2.0.0 uses 'git' property
            if any(k in item for k in ["source_control_uri", "source_control_branch", "source_control_tag"]):
                sc = {}
                if "source_control_uri" in item:
                    uri = item["source_control_uri"]
                    sc["git"] = uri if uri.endswith(".git") else f"{uri}.git"
                if "source_control_branch" in item:
                    sc["branch"] = item["source_control_branch"]
                if "source_control_tag" in item:
                    sc["tag"] = item["source_control_tag"]
                release["source_controls"] = [sc]
            
            if release:
                releases.append(release)
        
        if releases:
            output["releases"] = releases
    
    return output


def _add_platforms(output: dict, data: dict, is_overlay: bool = False) -> dict:
    """Add platforms to output."""
    if "platforms" in data:
        output["platforms"] = data["platforms"]
    elif is_overlay:
        output["platforms"] = []
    else:
        output["platforms"] = ["Windows", "Linux", "Mac", "iOS", "Android"]
    return output


def _upgrade_manifest_1_to_2(data: dict, output: dict, reversed_domain: str) -> dict:
    """Upgrade manifest from 1.0.0 to 2.0.0."""
    output["$schema"] = "https://canonical.o3de.org/o3de-manifest-2.0.0.json"
    
    # Manifest name
    old_name = data.get("o3de_manifest_name", "")
    if is_reverse_domain_format(old_name):
        new_name = old_name.lower()
    else:
        new_name = f"me.home.manifest.{old_name}".lower() if old_name else "me.home.manifest.default"
    
    output["o3de_manifest"] = {"name": new_name}
    
    # Default folders
    # Note: default_restricted_folder is NOT converted to overlays_path
    # because restricted and overlay are different concepts with no upgrade path
    output["default"] = {
        "engines_path": data.get("default_engines_folder", ""),
        "projects_path": data.get("default_projects_folder", ""),
        "gems_path": data.get("default_gems_folder", ""),
        "templates_path": data.get("default_templates_folder", ""),
        "repos_path": data.get("default_repos_folder", ""),
        "overlays_path": "",
        "third_party_path": data.get("default_third_party_folder", "")
    }
    
    # Country
    if "country" in data:
        output["country"] = data["country"]
    
    # Local and remote (manifest uses local, not children)
    output = _add_local_and_remote(output, data)
    
    return output


def _add_local_and_remote(output: dict, data: dict) -> dict:
    """Split collections into local (disk paths) and remote (URLs) for manifest."""
    local = {
        "engines": [],
        "projects": [],
        "gems": [],
        "templates": [],
        "repos": [],
        "overlays": []
    }
    remote = {
        "engines": [],
        "projects": [],
        "gems": [],
        "templates": [],
        "repos": [],
        "overlays": []
    }
    
    for key in ["engines", "projects", "gems", "templates", "repos"]:
        if key in data:
            loc, rem = _split_local_remote(data[key])
            if loc:
                json_file = key.rstrip("s") + ".json"
                local[key] = [
                    p if p.endswith(".json") else f"{p.rstrip('/\\')}/{json_file}"
                    for p in loc
                ]
            if rem:
                remote[key] = rem
    
    # Note: restricted/restricteds are NOT converted to overlays
    # They are a legacy concept with no upgrade path to 2.0.0
    
    # Handle external_subdirectories (assume gems)
    if "external_subdirectories" in data:
        loc, rem = _split_local_remote(data["external_subdirectories"])
        for p in loc:
            path = p if p.endswith(".json") else f"{p.rstrip('/\\')}/gem.json"
            if path not in local["gems"]:
                local["gems"].append(path)
        remote["gems"].extend(rem)
    
    # Handle pre-existing local section
    if "local" in data and isinstance(data["local"], dict):
        for key in ["engines", "projects"]:
            if key in data["local"]:
                loc, rem = _split_local_remote(data["local"][key])
                json_file = key.rstrip("s") + ".json"
                for p in loc:
                    path = p if p.endswith(".json") else f"{p.rstrip('/\\')}/{json_file}"
                    if path not in local[key]:
                        local[key].append(path)
                remote[key].extend(rem)
    
    output["local"] = local
    output["remote"] = remote
    return output


def _upgrade_engine_1_to_2(data: dict, output: dict, reversed_domain: str, is_o3de: bool) -> dict:
    """Upgrade engine from 1.0.0 to 2.0.0."""
    old_name = data.get("engine_name", "")
    new_name = _make_reverse_domain_name(old_name, "engine", reversed_domain)
    
    # Create engine objectHeader (NOT in origin - origin is for author info)
    output["engine"] = {
        "name": new_name,
        "version": data.get("version", "0.0.0"),
        "display_name": data.get("display_name", data.get("name", old_name)),
        "description": data.get("description", data.get("summary",
            data.get("display_name", data.get("name", old_name)))),
        "type": "engine",
        "id": data.get("engine_id", ""),
        "copyright_text": data.get("copyright_text", data.get("copyright", ""))
    }
    copyright_year = _get_copyright_year(data)
    if copyright_year is not None:
        output["engine"]["copyright_year"] = copyright_year
    
    # Add author origin and licenses
    output = _add_origin_and_licenses(output, data, is_o3de)
    output = _add_tags(output, data, "engine", new_name)
    output = _add_icon_and_docs(output, data)
    
    # O3DE engine-specific fields
    if "api_versions" in data:
        output["api_versions"] = data["api_versions"]
    
    # Handle restricted reference
    if "restricted" in data:
        restricted = data["restricted"]
        if is_reverse_domain_format(restricted):
            output["restricted"] = restricted
        else:
            output["restricted"] = f"{reversed_domain}.restricted.{restricted}".lower()
    
    # Add children for child objects (from external_subdirectories)
    output = _add_children_and_remote(output, data)
    output = _add_dependent_gems(output, data)
    output = _add_source_control(output, data)
    output = _add_download(output, data)
    output = _add_releases(output, data)
    output = _add_platforms(output, data)
    
    if "additional_info" in data:
        output["additional_info"] = data["additional_info"]
    if "requirements" in data:
        output["requirements"] = data["requirements"]
    
    return output


def _upgrade_project_1_to_2(data: dict, output: dict, reversed_domain: str, is_o3de: bool) -> dict:
    """Upgrade project from 1.0.0 to 2.0.0."""
    old_name = data.get("project_name", "")
    new_name = _make_reverse_domain_name(old_name, "project", reversed_domain)
    
    output["project"] = {
        "name": new_name,
        "version": data.get("version", "0.0.0"),
        "display_name": data.get("display_name", data.get("name", old_name)),
        "description": data.get("description", data.get("summary",
            data.get("display_name", data.get("name", old_name)))),
        "type": data.get("project_type", data.get("type", "")).lower(),
        "id": data.get("project_id", ""),
        "copyright_text": data.get("copyright_text", data.get("copyright", ""))
    }
    copyright_year = _get_copyright_year(data)
    if copyright_year is not None:
        output["project"]["copyright_year"] = copyright_year
    
    if "product_name" in data:
        output["product_name"] = data["product_name"]
    if "executable_name" in data:
        output["executable_name"] = data["executable_name"]
    
    # Handle engine reference
    if "engine" in data:
        engine = data["engine"]
        if ">=" in engine or "<=" in engine or "==" in engine:
            output["engine"] = engine
        elif is_reverse_domain_format(engine):
            output["engine"] = engine
        elif engine == "o3de":
            output["engine"] = "org.o3de.engine.o3de>=1.0.0"
        elif engine == "o3de-sdk":
            output["engine"] = "org.o3de.engine.o3de-sdk>=1.0.0"
        else:
            output["engine"] = f"org.o3de.engine.{engine}>=0.0.0".lower()
    
    output = _add_origin_and_licenses(output, data, is_o3de)
    output = _add_tags(output, data, "project", new_name)
    output = _add_icon_and_docs(output, data)
    output = _add_children_and_remote(output, data)
    output = _add_dependent_gems(output, data)
    output = _add_source_control(output, data)
    output = _add_download(output, data)
    output = _add_releases(output, data)
    output = _add_platforms(output, data)
    
    if "additional_info" in data:
        output["additional_info"] = data["additional_info"]
    if "requirements" in data:
        output["requirements"] = data["requirements"]
    
    return output


def _upgrade_gem_1_to_2(data: dict, output: dict, reversed_domain: str, is_o3de: bool) -> dict:
    """Upgrade gem from 1.0.0 to 2.0.0."""
    old_name = data.get("gem_name", "")
    new_name = _make_reverse_domain_name(old_name, "gem", reversed_domain)
    
    output["gem"] = {
        "name": new_name,
        "version": data.get("version", "0.0.0"),
        "display_name": data.get("display_name", data.get("name", old_name)),
        "description": data.get("description", data.get("summary",
            data.get("display_name", data.get("name", old_name)))),
        "type": data.get("gem_type", data.get("type", "")).lower(),
        "id": data.get("gem_id", ""),
        "copyright_text": data.get("copyright_text", data.get("copyright", ""))
    }
    copyright_year = _get_copyright_year(data)
    if copyright_year is not None:
        output["gem"]["copyright_year"] = copyright_year
    
    output = _add_origin_and_licenses(output, data, is_o3de)
    output = _add_tags(output, data, "gem", new_name)
    output = _add_icon_and_docs(output, data)
    output = _add_children_and_remote(output, data)
    output = _add_dependent_gems(output, data)
    output = _add_source_control(output, data)
    output = _add_download(output, data)
    output = _add_releases(output, data)
    output = _add_platforms(output, data)
    
    if "additional_info" in data:
        output["additional_info"] = data["additional_info"]
    if "requirements" in data:
        output["requirements"] = data["requirements"]
    
    return output


def _upgrade_template_1_to_2(data: dict, output: dict, reversed_domain: str, is_o3de: bool) -> dict:
    """Upgrade template from 1.0.0 to 2.0.0."""
    old_name = data.get("template_name", "")
    new_name = _make_reverse_domain_name(old_name, "template", reversed_domain)
    
    output["template"] = {
        "name": new_name,
        "version": data.get("version", "0.0.0"),
        "display_name": data.get("display_name", data.get("name", old_name)),
        "description": data.get("description", data.get("summary",
            data.get("display_name", data.get("name", old_name)))),
        "type": data.get("template_type", data.get("type", "")).lower(),
        "id": data.get("template_id", ""),
        "copyright_text": data.get("copyright_text", data.get("copyright", ""))
    }
    copyright_year = _get_copyright_year(data)
    if copyright_year is not None:
        output["template"]["copyright_year"] = copyright_year
    
    if "copyFiles" in data:
        output["copyFiles"] = data["copyFiles"]
    if "createDirectories" in data:
        output["createDirectories"] = data["createDirectories"]
    
    output = _add_origin_and_licenses(output, data, is_o3de)
    output = _add_tags(output, data, "template", new_name)
    output = _add_icon_and_docs(output, data)
    output = _add_children_and_remote(output, data)
    output = _add_dependent_gems(output, data)
    output = _add_source_control(output, data)
    output = _add_download(output, data)
    output = _add_releases(output, data)
    output = _add_platforms(output, data)
    
    if "additional_info" in data:
        output["additional_info"] = data["additional_info"]
    if "requirements" in data:
        output["requirements"] = data["requirements"]
    
    return output


def _upgrade_repo_1_to_2(data: dict, output: dict, reversed_domain: str, is_o3de: bool) -> dict:
    """Upgrade repo from 1.0.0 to 2.0.0."""
    old_name = data.get("repo_name", "")
    new_name = _make_reverse_domain_name(old_name, "repo", reversed_domain)
    
    output["repo"] = {
        "name": new_name,
        "version": data.get("version", "0.0.0"),
        "display_name": data.get("display_name", data.get("name", old_name)),
        "description": data.get("description", data.get("summary",
            data.get("display_name", data.get("name", old_name)))),
        "type": data.get("repo_type", data.get("type", "")).lower(),
        "id": data.get("repo_id", ""),
        "copyright_text": data.get("copyright_text", "")
    }
    copyright_year = _get_copyright_year(data)
    if copyright_year is not None:
        output["repo"]["copyright_year"] = copyright_year
    
    output = _add_origin_and_licenses(output, data, is_o3de)
    output = _add_tags(output, data, "repo", new_name)
    output = _add_icon_and_docs(output, data)
    output = _add_children_and_remote(output, data)
    
    return output


def _upgrade_overlay_1_to_2(data: dict, output: dict, reversed_domain: str, is_o3de: bool) -> dict:
    """Upgrade overlay (formerly restricted) from 1.0.0 to 2.0.0."""
    old_name = data.get("restricted_name", "")
    new_name = _make_reverse_domain_name(old_name, "overlay", reversed_domain)
    
    output["overlay"] = {
        "name": new_name,
        "version": data.get("version", "0.0.0"),
        "display_name": data.get("display_name", data.get("name", old_name)),
        "description": data.get("description", data.get("summary",
            data.get("display_name", data.get("name", old_name)))),
        "type": data.get("restricted_type", data.get("type", "")).lower(),
        "id": data.get("restricted_id", ""),
        "copyright_text": data.get("copyright_text", data.get("copyright", ""))
    }
    copyright_year = _get_copyright_year(data)
    if copyright_year is not None:
        output["overlay"]["copyright_year"] = copyright_year
    
    output["extends"] = data.get("extends", "")
    output["precedence"] = data.get("precedence", 0)
    output["platform_maps"] = data.get("platform_maps", [])
    output["platform_wart_maps"] = data.get("platform_wart_maps", [])
    
    output = _add_origin_and_licenses(output, data, is_o3de)
    output = _add_tags(output, data, "overlay", new_name)
    output = _add_icon_and_docs(output, data)
    output = _add_platforms(output, data, is_overlay=True)
    
    if "additional_info" in data:
        output["additional_info"] = data["additional_info"]
    if "requirements" in data:
        output["requirements"] = data["requirements"]
    
    return output


# ============================================================================
# Full Upgrade Path
# ============================================================================

def upgrade_to_latest(
    data: dict,
    object_type: Optional[str] = None,
) -> Optional[dict]:
    """
    Upgrade data to latest schema version (2.0.0).
    
    Args:
        data: Object data dict
        object_type: Optional type hint (auto-detected if not provided)
    
    Returns:
        Upgraded data dict, or None if the object type should be skipped
        (e.g., 'restricted' objects have no upgrade path to 2.0.0)
    """
    current_type, current_version = get_schema_version(data)
    
    if object_type:
        current_type = object_type
    
    if current_type == "unknown":
        raise UpgradeError("Cannot detect object type for upgrade")
    
    # Restricted objects have no upgrade path to 2.0.0
    if current_type == "restricted":
        return None
    
    upgraded = data
    
    # Upgrade 0 → 1.0.0
    if current_version == "0":
        upgraded = upgrade_0_to_1(upgraded, current_type)
        current_version = "1.0.0"
    
    # Upgrade 1.0.0 → 2.0.0
    if current_version in ("1.0", "1.0.0"):
        upgraded = upgrade_1_to_2(upgraded, current_type)
        if upgraded is None:
            return None
        current_version = "2.0.0"
    
    return upgraded


def upgrade_file(
    path: Path,
    backup: bool = True,
) -> tuple[Path, str, str] | None:
    """
    Upgrade a single JSON file to latest schema.
    
    Args:
        path: Path to JSON file
        backup: Create .bak backup before modifying
    
    Returns:
        Tuple of (path, old_version, new_version), or None if skipped
    """
    with open(path, "r") as f:
        data = json.load(f)
    
    old_type, old_version = get_schema_version(data)
    
    if not needs_upgrade(data):
        return (path, old_version, old_version)
    
    # Upgrade
    upgraded = upgrade_to_latest(data, old_type)
    
    # Skip objects with no upgrade path (e.g., restricted)
    if upgraded is None:
        logger.info(f"Skipped {path}: {old_type} objects have no upgrade path to 2.0.0")
        return None
    
    # Backup (only if we're actually upgrading)
    if backup:
        backup_path = path.with_suffix(f".{old_version}.bak.json")
        shutil.copy(path, backup_path)
        logger.info(f"Backed up: {backup_path}")
    
    new_type, new_version = get_schema_version(upgraded)
    
    # Write
    with open(path, "w") as f:
        json.dump(upgraded, f, indent=2)
    
    logger.info(f"Upgraded {path}: {old_version} → {new_version}")
    return (path, old_version, new_version)


def upgrade_directory(
    root: Path,
    recursive: bool = True,
    backup: bool = True,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> list[tuple[Path, str, str]]:
    """
    Upgrade all O3DE JSON files in a directory.
    
    Args:
        root: Root directory to scan
        recursive: Search recursively
        backup: Create backups
        progress_callback: Progress callback
    
    Returns:
        List of (path, old_version, new_version) for upgraded files
    """
    json_files = ["engine.json", "project.json", "gem.json", "template.json", 
                  "repo.json", "restricted.json", "overlay.json"]
    
    paths = []
    if recursive:
        for pattern in json_files:
            paths.extend(root.rglob(pattern))
    else:
        for pattern in json_files:
            candidate = root / pattern
            if candidate.exists():
                paths.append(candidate)
    
    results = []
    total = len(paths)
    
    for i, path in enumerate(paths, 1):
        if progress_callback:
            progress_callback(f"Upgrading {path.name}", i, total)
        
        try:
            result = upgrade_file(path, backup=backup)
            # Skip None results (e.g., restricted.json files)
            if result is not None and result[1] != result[2]:
                results.append(result)
        except Exception as e:
            logger.warning(f"Failed to upgrade {path}: {e}")
    
    return results
