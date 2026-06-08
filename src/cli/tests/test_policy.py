# O3DE Pilot - Policy Enforcement Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for O3: license compliance, security advisories, deprecation."""

import pytest
from o3de_pilot.core.policy import (
    PolicyConfig,
    PolicyViolation,
    check_object_policy,
    check_install_policy,
    PERMISSIVE_LICENSES,
    COPYLEFT_LICENSES,
)


def _gem(name="org.test.gem", version="1.0.0", licenses=None, deprecated=None):
    data = {
        "$schemaVersion": "2.0.0",
        "gem": {"name": name, "version": version},
    }
    if deprecated:
        data["gem"]["deprecated"] = deprecated
    if licenses is not None:
        data["licenses"] = licenses
    return data


class TestLicenseCompliance:
    def test_no_license_default_warning(self):
        v = check_object_policy(_gem(licenses=None))
        assert any(v2.category == "license" and v2.severity == "warning" for v2 in v)

    def test_no_license_required_error(self):
        policy = PolicyConfig(require_license=True)
        v = check_object_policy(_gem(licenses=None), policy)
        assert any(v2.category == "license" and v2.severity == "error" for v2 in v)

    def test_permissive_license_passes(self):
        policy = PolicyConfig(require_license=True)
        v = check_object_policy(_gem(licenses=[{"name": "Apache-2.0"}]), policy)
        assert not any(v2.severity == "error" for v2 in v)

    def test_denied_license_blocked(self):
        policy = PolicyConfig(denied_licenses={"SSPL-1.0"})
        v = check_object_policy(_gem(licenses=[{"name": "SSPL-1.0"}]), policy)
        assert any(v2.severity == "error" and "denied" in v2.message for v2 in v)

    def test_allowed_list_blocks_unlisted(self):
        policy = PolicyConfig(allowed_licenses={"Apache-2.0", "MIT"})
        v = check_object_policy(_gem(licenses=[{"name": "BSD-3-Clause"}]), policy)
        assert any(v2.severity == "error" and "not in the allowed list" in v2.message for v2 in v)

    def test_allowed_list_passes_listed(self):
        policy = PolicyConfig(allowed_licenses={"Apache-2.0", "MIT"})
        v = check_object_policy(_gem(licenses=[{"name": "MIT"}]), policy)
        assert not any(v2.severity == "error" for v2 in v)

    def test_copyleft_allowed_by_default(self):
        v = check_object_policy(_gem(licenses=[{"name": "GPL-3.0-only"}]))
        assert not any(v2.category == "license" and v2.severity == "error" for v2 in v)

    def test_copyleft_blocked_when_disabled(self):
        policy = PolicyConfig(allow_copyleft=False)
        v = check_object_policy(_gem(licenses=[{"name": "GPL-3.0-only"}]), policy)
        assert any(v2.severity == "error" and "Copyleft" in v2.message for v2 in v)

    def test_string_license_format(self):
        v = check_object_policy(_gem(licenses=["Apache-2.0"]))
        assert not any(v2.severity == "error" for v2 in v)


class TestDeprecation:
    def test_deprecated_warning_by_default(self):
        v = check_object_policy(_gem(deprecated="Use org.test.gem.v2 instead"))
        assert any(v2.category == "deprecation" and v2.severity == "warning" for v2 in v)

    def test_deprecated_error_when_blocked(self):
        policy = PolicyConfig(allow_deprecated=False)
        v = check_object_policy(_gem(deprecated="Use v2"), policy)
        assert any(v2.category == "deprecation" and v2.severity == "error" for v2 in v)

    def test_not_deprecated_passes(self):
        v = check_object_policy(_gem())
        assert not any(v2.category == "deprecation" for v2 in v)


class TestSecurityAdvisories:
    def test_matching_advisory_flagged(self):
        policy = PolicyConfig(security_advisories=[{
            "name": "org.test.gem",
            "versions": ["1.0.0"],
            "severity": "error",
            "description": "Remote code execution vulnerability",
        }])
        v = check_object_policy(_gem(), policy)
        assert any(v2.category == "security" for v2 in v)

    def test_advisory_different_version_passes(self):
        policy = PolicyConfig(security_advisories=[{
            "name": "org.test.gem",
            "versions": ["0.9.0"],
            "severity": "error",
            "description": "Old vulnerability",
        }])
        v = check_object_policy(_gem(version="1.0.0"), policy)
        assert not any(v2.category == "security" for v2 in v)

    def test_advisory_all_versions(self):
        policy = PolicyConfig(security_advisories=[{
            "name": "org.test.gem",
            "versions": [],  # all versions
            "severity": "warning",
            "description": "Known issue",
        }])
        v = check_object_policy(_gem(version="5.0.0"), policy)
        assert any(v2.category == "security" for v2 in v)

    def test_advisory_different_object_passes(self):
        policy = PolicyConfig(security_advisories=[{
            "name": "org.other.gem",
            "versions": ["1.0.0"],
            "severity": "error",
            "description": "Not our gem",
        }])
        v = check_object_policy(_gem(), policy)
        assert not any(v2.category == "security" for v2 in v)


class TestBatchPolicy:
    def test_check_install_policy_multiple(self):
        policy = PolicyConfig(require_license=True)
        objects = [
            _gem(name="org.a", licenses=[{"name": "MIT"}]),
            _gem(name="org.b", licenses=None),
            _gem(name="org.c", licenses=[{"name": "Apache-2.0"}]),
        ]
        v = check_install_policy(objects, policy)
        errors = [x for x in v if x.severity == "error"]
        assert len(errors) == 1
        assert errors[0].object_name == "org.b"


class TestPolicyConfig:
    def test_from_dict(self):
        cfg = PolicyConfig.from_dict({
            "allowed_licenses": ["MIT", "Apache-2.0"],
            "denied_licenses": ["SSPL-1.0"],
            "allow_deprecated": False,
            "allow_copyleft": False,
            "require_license": True,
        })
        assert cfg.allowed_licenses == {"MIT", "Apache-2.0"}
        assert cfg.denied_licenses == {"SSPL-1.0"}
        assert cfg.allow_deprecated is False
        assert cfg.allow_copyleft is False
        assert cfg.require_license is True

    def test_to_dict_roundtrip(self):
        cfg = PolicyConfig(
            allowed_licenses={"MIT"},
            denied_licenses={"GPL-3.0-only"},
            allow_deprecated=False,
        )
        d = cfg.to_dict()
        cfg2 = PolicyConfig.from_dict(d)
        assert cfg2.allowed_licenses == {"MIT"}
        assert cfg2.denied_licenses == {"GPL-3.0-only"}

    def test_load_from_file(self, tmp_path):
        import json
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"require_license": True, "allow_copyleft": False}))
        cfg = PolicyConfig.load(p)
        assert cfg.require_license is True
        assert cfg.allow_copyleft is False

    def test_load_missing_file_defaults(self, tmp_path):
        cfg = PolicyConfig.load(tmp_path / "nope.json")
        assert cfg.require_license is False
        assert cfg.allow_copyleft is True


class TestPolicyViolation:
    def test_to_dict(self):
        v = PolicyViolation("error", "license", "Bad license", "org.test.gem")
        d = v.to_dict()
        assert d["severity"] == "error"
        assert d["category"] == "license"
        assert d["object_name"] == "org.test.gem"


class TestLicenseConstants:
    def test_permissive_licenses_populated(self):
        assert "Apache-2.0" in PERMISSIVE_LICENSES
        assert "MIT" in PERMISSIVE_LICENSES

    def test_copyleft_licenses_populated(self):
        assert "GPL-3.0-only" in COPYLEFT_LICENSES
        assert "LGPL-2.1-or-later" in COPYLEFT_LICENSES
