# O3DE Pilot - Git Utilities Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.git_utils module."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from o3de_pilot.core.git_utils import (
    normalize_git_url,
    is_git_url,
    get_local_git_remote,
    get_local_git_branch,
    is_url_cloned_locally,
    parse_github_url,
    clear_branch_cache,
    clear_releases_cache,
)


class TestNormalizeGitUrl:
    """Test git URL normalization."""

    def test_https_with_git_extension(self):
        result = normalize_git_url("https://github.com/owner/repo.git")
        assert result == "https://github.com/owner/repo"

    def test_https_without_git_extension(self):
        result = normalize_git_url("https://github.com/owner/repo")
        assert result == "https://github.com/owner/repo"

    def test_ssh_format(self):
        result = normalize_git_url("git@github.com:owner/repo.git")
        assert result == "https://github.com/owner/repo"

    def test_trailing_slash(self):
        result = normalize_git_url("https://github.com/owner/repo/")
        assert result == "https://github.com/owner/repo"

    def test_empty_url(self):
        assert normalize_git_url("") == ""

    def test_lowercase(self):
        result = normalize_git_url("https://GitHub.COM/Owner/Repo")
        assert result == "https://github.com/owner/repo"

    def test_ssh_without_git(self):
        result = normalize_git_url("git@gitlab.com:org/project")
        assert result == "https://gitlab.com/org/project"


class TestIsGitUrl:
    """Test git URL detection."""

    def test_github_https(self):
        assert is_git_url("https://github.com/owner/repo") is True

    def test_gitlab_https(self):
        assert is_git_url("https://gitlab.com/owner/repo") is True

    def test_ssh_url(self):
        assert is_git_url("git@github.com:owner/repo.git") is True

    def test_git_extension(self):
        assert is_git_url("https://example.com/repo.git") is True

    def test_non_git_url(self):
        assert is_git_url("https://example.com/page.html") is False

    def test_empty_url(self):
        assert is_git_url("") is False

    def test_none_url(self):
        assert is_git_url(None) is False

    def test_bitbucket(self):
        assert is_git_url("https://bitbucket.org/team/repo") is True

    def test_azure_devops(self):
        assert is_git_url("https://dev.azure.com/org/project/_git/repo") is True


class TestGetLocalGitRemote:
    """Test getting local git remote URL."""

    @patch("o3de_pilot.core.git_utils.subprocess.run")
    def test_returns_remote_url(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/owner/repo.git\n",
        )
        result = get_local_git_remote("/some/path")
        assert result == "https://github.com/owner/repo.git"

    @patch("o3de_pilot.core.git_utils.subprocess.run")
    def test_returns_none_for_non_git(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = get_local_git_remote("/not/a/repo")
        assert result is None

    def test_returns_none_for_empty_path(self):
        assert get_local_git_remote("") is None

    def test_returns_none_for_none_path(self):
        assert get_local_git_remote(None) is None

    @patch("o3de_pilot.core.git_utils.subprocess.run", side_effect=FileNotFoundError)
    def test_handles_git_not_found(self, mock_run):
        result = get_local_git_remote("/some/path")
        assert result is None

    @patch("o3de_pilot.core.git_utils.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5))
    def test_handles_timeout(self, mock_run):
        result = get_local_git_remote("/some/path")
        assert result is None


class TestGetLocalGitBranch:
    """Test getting current git branch."""

    @patch("o3de_pilot.core.git_utils.subprocess.run")
    def test_returns_branch_name(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        result = get_local_git_branch("/some/path")
        assert result == "main"

    @patch("o3de_pilot.core.git_utils.subprocess.run")
    def test_detached_head_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="HEAD\n")
        result = get_local_git_branch("/some/path")
        assert result is None

    @patch("o3de_pilot.core.git_utils.subprocess.run")
    def test_non_repo_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = get_local_git_branch("/not/a/repo")
        assert result is None

    def test_empty_path_returns_none(self):
        assert get_local_git_branch("") is None


class TestIsUrlClonedLocally:
    """Test URL clone detection."""

    def test_matching_url(self):
        local_urls = {"https://github.com/owner/repo"}
        assert is_url_cloned_locally("https://github.com/owner/repo.git", local_urls) is True

    def test_non_matching_url(self):
        local_urls = {"https://github.com/owner/other"}
        assert is_url_cloned_locally("https://github.com/owner/repo", local_urls) is False

    def test_empty_url(self):
        assert is_url_cloned_locally("", {"https://github.com/a/b"}) is False

    def test_empty_local_urls(self):
        assert is_url_cloned_locally("https://github.com/a/b", set()) is False

    def test_ssh_matches_https(self):
        local_urls = {"https://github.com/owner/repo"}
        assert is_url_cloned_locally("git@github.com:owner/repo.git", local_urls) is True


class TestParseGithubUrl:
    """Test GitHub URL parsing."""

    def test_https_url(self):
        result = parse_github_url("https://github.com/owner/repo")
        assert result == ("owner", "repo")

    def test_ssh_url(self):
        result = parse_github_url("git@github.com:owner/repo.git")
        assert result == ("owner", "repo")

    def test_non_github_returns_none(self):
        assert parse_github_url("https://gitlab.com/owner/repo") is None

    def test_empty_url(self):
        assert parse_github_url("") is None

    def test_none_url(self):
        assert parse_github_url(None) is None

    def test_url_with_extra_path(self):
        result = parse_github_url("https://github.com/owner/repo/tree/main")
        assert result == ("owner", "repo")


class TestCacheClear:
    """Test cache clearing functions."""

    def test_clear_branch_cache(self):
        """Should not raise."""
        clear_branch_cache()

    def test_clear_releases_cache(self):
        """Should not raise."""
        clear_releases_cache()
