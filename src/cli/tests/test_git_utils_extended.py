# O3DE Pilot - Extended Git Utilities Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Extended tests for o3de_pilot.core.git_utils — covers uncovered functions."""

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from o3de_pilot.core.git_utils import (
    get_default_branch,
    get_local_git_upstream,
    get_github_releases,
    get_github_releases_full,
    clear_branch_cache,
    clear_releases_cache,
)


# ---------------------------------------------------------------------------
# TestGetDefaultBranch
# ---------------------------------------------------------------------------

class TestGetDefaultBranch:
    """Test get_default_branch function."""

    def setup_method(self):
        clear_branch_cache()

    def test_empty_url_returns_none(self):
        assert get_default_branch("") is None

    def test_success_main(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ref: refs/heads/main\tHEAD\nabc123\tHEAD\n"

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result):
            branch = get_default_branch("https://github.com/test/repo.git")

        assert branch == "main"

    def test_success_development(self):
        clear_branch_cache()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ref: refs/heads/development\tHEAD\nabc123\tHEAD\n"

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result):
            branch = get_default_branch("https://github.com/test/repo2.git")

        assert branch == "development"

    def test_non_zero_return(self):
        clear_branch_cache()
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: not found"
        mock_result.stdout = ""

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result):
            assert get_default_branch("https://github.com/test/nope.git") is None

    def test_timeout(self):
        clear_branch_cache()
        with patch(
            "o3de_pilot.core.git_utils.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            assert get_default_branch("https://github.com/test/slow.git") is None

    def test_git_not_found(self):
        clear_branch_cache()
        with patch(
            "o3de_pilot.core.git_utils.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            assert get_default_branch("https://github.com/test/nogit.git") is None

    def test_unparseable_output(self):
        clear_branch_cache()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123\tHEAD\n"  # No ref: line

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result):
            assert get_default_branch("https://github.com/test/noref.git") is None

    def test_appends_dot_git_if_missing(self):
        clear_branch_cache()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ref: refs/heads/main\tHEAD\n"

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result) as mock_run:
            get_default_branch("https://github.com/test/nodotext")

        called_url = mock_run.call_args[0][0][3]  # 4th arg after git, ls-remote, --symref
        assert called_url.endswith(".git")


# ---------------------------------------------------------------------------
# TestGetLocalGitUpstream
# ---------------------------------------------------------------------------

class TestGetLocalGitUpstream:
    """Test get_local_git_upstream function."""

    def test_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/upstream/repo.git\n"

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result):
            assert get_local_git_upstream("/some/path") == "https://github.com/upstream/repo.git"

    def test_no_upstream(self):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: No such remote 'upstream'"

        with patch("o3de_pilot.core.git_utils.subprocess.run", return_value=mock_result):
            assert get_local_git_upstream("/some/path") is None

    def test_empty_path(self):
        assert get_local_git_upstream("") is None

    def test_none_path(self):
        assert get_local_git_upstream(None) is None

    def test_timeout(self):
        with patch(
            "o3de_pilot.core.git_utils.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5),
        ):
            assert get_local_git_upstream("/some/path") is None


# ---------------------------------------------------------------------------
# TestGetGithubReleases
# ---------------------------------------------------------------------------

class TestGetGithubReleases:
    """Test get_github_releases function."""

    def setup_method(self):
        clear_releases_cache()

    def test_non_github_returns_empty(self):
        assert get_github_releases("https://gitlab.com/owner/repo") == []

    def test_empty_url_returns_empty(self):
        assert get_github_releases("") == []

    def test_success(self):
        releases = [
            {"tag_name": "v2.0.0"},
            {"tag_name": "v1.0.0"},
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = __import__("json").dumps(releases).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_github_releases("https://github.com/test/repo")

        assert result == ["v2.0.0", "v1.0.0"]

    def test_api_error_returns_empty(self):
        clear_releases_cache()
        with patch("urllib.request.urlopen", side_effect=Exception("API down")):
            assert get_github_releases("https://github.com/test/err") == []


# ---------------------------------------------------------------------------
# TestGetGithubReleasesFull
# ---------------------------------------------------------------------------

class TestGetGithubReleasesFull:
    """Test get_github_releases_full function."""

    def setup_method(self):
        clear_releases_cache()

    def test_non_github_returns_empty(self):
        assert get_github_releases_full("https://gitlab.com/owner/repo") == []

    def test_success_with_assets(self):
        releases = [
            {
                "tag_name": "v1.0.0",
                "zipball_url": "https://api.github.com/repos/x/y/zipball/v1.0.0",
                "tarball_url": "https://api.github.com/repos/x/y/tarball/v1.0.0",
                "assets": [
                    {
                        "name": "binary.zip",
                        "browser_download_url": "https://github.com/x/y/releases/download/v1.0.0/binary.zip",
                        "digest": "sha256:abc",
                    }
                ],
            }
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = __import__("json").dumps(releases).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_github_releases_full("https://github.com/x/y")

        assert len(result) == 1
        assert result[0]["tag_name"] == "v1.0.0"
        assert len(result[0]["assets"]) == 1
        assert result[0]["assets"][0]["name"] == "binary.zip"

    def test_skips_release_without_tag(self):
        clear_releases_cache()
        releases = [
            {"tag_name": "", "zipball_url": ""},
            {"tag_name": "v1.0.0", "zipball_url": "z"},
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = __import__("json").dumps(releases).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_github_releases_full("https://github.com/x/y2")

        assert len(result) == 1

    def test_api_error_returns_empty(self):
        clear_releases_cache()
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            assert get_github_releases_full("https://github.com/x/y3") == []
