# O3DE Pilot - Policy Enforcement
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Policy enforcement for O3DE object installation.

Checks license compatibility, security advisories, and deprecation
status before allowing installation of objects.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# SPDX license IDs considered permissive/compatible
PERMISSIVE_LICENSES = {
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Zlib",
    "Unlicense",
    "CC0-1.0",
    "0BSD",
    "BlueOak-1.0.0",
}

# Licenses that require special handling
COPYLEFT_LICENSES = {
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "MPL-2.0",
    "EUPL-1.2",
}


class PolicyViolation:
    """Represents a policy violation."""

    def __init__(self, severity: str, category: str, message: str, object_name: str = ""):
        self.severity = severity  # "error", "warning", "info"
        self.category = category  # "license", "security", "deprecation"
        self.message = message
        self.object_name = object_name

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "object_name": self.object_name,
        }


class PolicyConfig:
    """Policy configuration for a workspace or manifest."""

    def __init__(
        self,
        allowed_licenses: Optional[set[str]] = None,
        denied_licenses: Optional[set[str]] = None,
        allow_deprecated: bool = True,
        allow_copyleft: bool = True,
        require_license: bool = False,
        security_advisories: Optional[list[dict]] = None,
    ):
        self.allowed_licenses = allowed_licenses
        self.denied_licenses = denied_licenses or set()
        self.allow_deprecated = allow_deprecated
        self.allow_copyleft = allow_copyleft
        self.require_license = require_license
        self.security_advisories = security_advisories or []

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyConfig":
        return cls(
            allowed_licenses=set(data["allowed_licenses"]) if "allowed_licenses" in data else None,
            denied_licenses=set(data.get("denied_licenses", [])),
            allow_deprecated=data.get("allow_deprecated", True),
            allow_copyleft=data.get("allow_copyleft", True),
            require_license=data.get("require_license", False),
            security_advisories=data.get("security_advisories", []),
        )

    @classmethod
    def load(cls, path: Path) -> "PolicyConfig":
        """Load policy config from a JSON file."""
        if path.exists():
            with open(path) as f:
                return cls.from_dict(json.load(f))
        return cls()

    def to_dict(self) -> dict:
        d: dict = {}
        if self.allowed_licenses is not None:
            d["allowed_licenses"] = sorted(self.allowed_licenses)
        if self.denied_licenses:
            d["denied_licenses"] = sorted(self.denied_licenses)
        d["allow_deprecated"] = self.allow_deprecated
        d["allow_copyleft"] = self.allow_copyleft
        d["require_license"] = self.require_license
        if self.security_advisories:
            d["security_advisories"] = self.security_advisories
        return d


def check_object_policy(
    object_data: dict,
    policy: Optional[PolicyConfig] = None,
) -> list[PolicyViolation]:
    """Check an object against policy rules.

    Args:
        object_data: The object JSON data
        policy: Policy configuration (uses defaults if None)

    Returns:
        List of policy violations (empty = passes)
    """
    if policy is None:
        policy = PolicyConfig()

    violations: list[PolicyViolation] = []
    obj_name = _extract_name(object_data)

    # License checks
    violations.extend(_check_licenses(object_data, policy, obj_name))

    # Deprecation check
    violations.extend(_check_deprecation(object_data, policy, obj_name))

    # Security advisory check
    violations.extend(_check_security(object_data, policy, obj_name))

    return violations


def check_install_policy(
    objects: list[dict],
    policy: Optional[PolicyConfig] = None,
) -> list[PolicyViolation]:
    """Check multiple objects against policy before installation.

    Args:
        objects: List of object JSON data dicts
        policy: Policy configuration

    Returns:
        List of all policy violations across all objects
    """
    violations = []
    for obj in objects:
        violations.extend(check_object_policy(obj, policy))
    return violations


def _check_licenses(
    data: dict, policy: PolicyConfig, obj_name: str
) -> list[PolicyViolation]:
    """Check license compliance."""
    violations = []
    licenses = data.get("licenses", [])

    if not licenses:
        if policy.require_license:
            violations.append(PolicyViolation(
                "error", "license",
                f"No license specified — required by policy",
                obj_name,
            ))
        else:
            violations.append(PolicyViolation(
                "warning", "license",
                f"No license specified",
                obj_name,
            ))
        return violations

    for lic in licenses:
        lic_id = lic.get("name", lic) if isinstance(lic, dict) else str(lic)

        # Check denied list
        if lic_id in policy.denied_licenses:
            violations.append(PolicyViolation(
                "error", "license",
                f"License '{lic_id}' is denied by policy",
                obj_name,
            ))

        # Check allowed list (if set, only these are permitted)
        if policy.allowed_licenses is not None and lic_id not in policy.allowed_licenses:
            violations.append(PolicyViolation(
                "error", "license",
                f"License '{lic_id}' is not in the allowed list",
                obj_name,
            ))

        # Check copyleft
        if not policy.allow_copyleft and lic_id in COPYLEFT_LICENSES:
            violations.append(PolicyViolation(
                "error", "license",
                f"Copyleft license '{lic_id}' is not allowed by policy",
                obj_name,
            ))

    return violations


def _check_deprecation(
    data: dict, policy: PolicyConfig, obj_name: str
) -> list[PolicyViolation]:
    """Check deprecation status."""
    violations = []

    # Check in object header
    for key in ["engine", "gem", "project", "template", "repo", "overlay"]:
        header = data.get(key, {})
        if isinstance(header, dict) and header.get("deprecated"):
            if not policy.allow_deprecated:
                violations.append(PolicyViolation(
                    "error", "deprecation",
                    f"Object is deprecated: {header['deprecated']}",
                    obj_name,
                ))
            else:
                violations.append(PolicyViolation(
                    "warning", "deprecation",
                    f"Object is deprecated: {header['deprecated']}",
                    obj_name,
                ))
            break

    # Also check top-level deprecated field
    if data.get("deprecated"):
        if not policy.allow_deprecated:
            violations.append(PolicyViolation(
                "error", "deprecation",
                f"Object is deprecated: {data['deprecated']}",
                obj_name,
            ))

    return violations


def _check_security(
    data: dict, policy: PolicyConfig, obj_name: str
) -> list[PolicyViolation]:
    """Check against known security advisories."""
    violations = []

    for advisory in policy.security_advisories:
        affected_name = advisory.get("name", "")
        affected_versions = advisory.get("versions", [])
        severity = advisory.get("severity", "error")
        description = advisory.get("description", "Security advisory")

        if obj_name == affected_name:
            obj_version = _extract_version(data)
            if not affected_versions or obj_version in affected_versions:
                violations.append(PolicyViolation(
                    severity, "security",
                    f"Security advisory: {description}",
                    obj_name,
                ))

    return violations


def _extract_name(data: dict) -> str:
    """Extract the object name from data."""
    for key in ["engine", "gem", "project", "template", "repo", "overlay"]:
        header = data.get(key, {})
        if isinstance(header, dict) and header.get("name"):
            return header["name"]
    return data.get("name", data.get("engine_name", data.get("gem_name", "")))


def _extract_version(data: dict) -> str:
    """Extract the object version from data."""
    for key in ["engine", "gem", "project", "template", "repo", "overlay"]:
        header = data.get(key, {})
        if isinstance(header, dict) and header.get("version"):
            return header["version"]
    return data.get("version", "")
