"""
Tests for GitHubProjectDownloader and GitLabProjectDownloader.

Covers:
- get_github_project_path / get_project_path_with_namespace URL parsing helpers
- GitHubProjectDownloader / GitLabProjectDownloader initialisation
- download_project: happy path (shallow + full clone), error handling
- _download_project: correct subprocess args, cwd, shallow/full, token handling
- download_to_permanent_location: flat vs nested structure, error handling
- No os.chdir() calls — all directory context passes via cwd=
- Timeout and CalledProcessError are re-raised / returned as None appropriately
"""

import os
import subprocess
import tempfile
from pathlib import Path, PurePath
from unittest.mock import MagicMock, call, patch

import pytest

from gsast_core.repolib.downloader.github_downloader import (
    GitHubProjectDownloader,
    get_github_project_path,
)
from gsast_core.repolib.downloader.gitlab_downloader import (
    GitLabProjectDownloader,
    get_project_path_with_namespace,
)


# ---------------------------------------------------------------------------
# URL-parsing helpers
# ---------------------------------------------------------------------------


class TestGetGithubProjectPath:
    def test_https_url_with_dot_git(self):
        assert get_github_project_path("https://github.com/owner/repo.git") == PurePath("owner/repo")

    def test_https_url_without_dot_git(self):
        assert get_github_project_path("https://github.com/owner/repo") == PurePath("owner/repo")

    def test_ssh_url(self):
        assert get_github_project_path("git@github.com:owner/repo.git") == PurePath("owner/repo")

    def test_ssh_url_without_dot_git(self):
        assert get_github_project_path("git@github.com:owner/repo") == PurePath("owner/repo")

    def test_nested_org_path(self):
        assert get_github_project_path("https://github.com/google/truth.git") == PurePath("google/truth")

    def test_unsupported_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported GitHub URL format"):
            get_github_project_path("https://bitbucket.org/owner/repo.git")


class TestGetProjectPathWithNamespace:
    def test_ssh_url(self):
        assert get_project_path_with_namespace("git@gitlab.com:group/project.git") == PurePath("group/project")

    def test_nested_namespace(self):
        assert get_project_path_with_namespace("git@gitlab.example.com:a/b/c.git") == PurePath("a/b/c")

    def test_path_object_is_handled(self):
        result = get_project_path_with_namespace(Path("git@gitlab.com:owner/repo.git"))
        assert result == PurePath("owner/repo")


# ---------------------------------------------------------------------------
# GitHubProjectDownloader — initialisation
# ---------------------------------------------------------------------------


class TestGitHubProjectDownloaderInit:
    def test_stores_token(self):
        d = GitHubProjectDownloader(GITHUB_API_TOKEN="tok123")
        assert d.GITHUB_API_TOKEN == "tok123"

    def test_no_token_defaults_to_none(self):
        d = GitHubProjectDownloader()
        assert d.GITHUB_API_TOKEN is None

    def test_temp_dir_is_created(self):
        d = GitHubProjectDownloader()
        assert os.path.isdir(d.temp_dir)

    def test_git_lfs_env_set(self):
        GitHubProjectDownloader()
        assert os.environ.get("GIT_LFS_SKIP_SMUDGE") == "1"

    def test_get_project_path_delegates_to_helper(self):
        d = GitHubProjectDownloader()
        assert d.get_project_path("https://github.com/owner/repo.git") == PurePath("owner/repo")


# ---------------------------------------------------------------------------
# GitHubProjectDownloader — _download_project subprocess args
# ---------------------------------------------------------------------------


class TestGitHubDownloadProjectSubprocess:
    """Verify that _download_project constructs the correct subprocess call."""

    def _make_result(self, stdout="", returncode=0):
        r = MagicMock()
        r.stdout = stdout
        r.returncode = returncode
        return r

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_shallow_clone_args(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader()
        d._download_project("https://github.com/owner/repo.git", Path("/tmp/dest"), use_shallow_clone=True)

        args = mock_run.call_args[0][0]
        assert "--depth=1" in args
        assert "--single-branch" in args

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_full_clone_omits_depth_flag(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader()
        d._download_project("https://github.com/owner/repo.git", Path("/tmp/dest"), use_shallow_clone=False)

        args = mock_run.call_args[0][0]
        assert "--depth=1" not in args
        assert "--single-branch" not in args

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_cwd_is_passed_not_chdir(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader()
        dest = Path("/tmp/some/dest")
        d._download_project("https://github.com/owner/repo.git", dest, use_shallow_clone=True)

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == str(dest)

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_no_os_chdir_called(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader()
        with patch("os.chdir") as mock_chdir:
            d._download_project("https://github.com/owner/repo.git", Path("/tmp/d"), use_shallow_clone=True)
            mock_chdir.assert_not_called()

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_https_url_with_token_injected(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader(GITHUB_API_TOKEN="mytoken")
        d._download_project("https://github.com/owner/repo.git", Path("/tmp/d"), use_shallow_clone=True)

        args = mock_run.call_args[0][0]
        url_arg = args[-1]
        assert "mytoken@github.com" in url_arg

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_ssh_url_converted_to_https_with_token(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader(GITHUB_API_TOKEN="mytoken")
        d._download_project("git@github.com:owner/repo.git", Path("/tmp/d"), use_shallow_clone=True)

        args = mock_run.call_args[0][0]
        url_arg = args[-1]
        assert url_arg.startswith("https://mytoken@github.com/")

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_no_token_uses_original_url(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitHubProjectDownloader()
        original_url = "https://github.com/owner/repo.git"
        d._download_project(original_url, Path("/tmp/d"), use_shallow_clone=False)

        args = mock_run.call_args[0][0]
        assert original_url in args

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_called_process_error_is_reraised(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git", stderr="fatal: repo not found")
        d = GitHubProjectDownloader()
        with pytest.raises(subprocess.CalledProcessError):
            d._download_project("https://github.com/owner/repo.git", Path("/tmp/d"), use_shallow_clone=True)

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_timeout_expired_is_reraised(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 300)
        d = GitHubProjectDownloader()
        with pytest.raises(subprocess.TimeoutExpired):
            d._download_project("https://github.com/owner/repo.git", Path("/tmp/d"), use_shallow_clone=True)


# ---------------------------------------------------------------------------
# GitHubProjectDownloader — download_project (integration-style with real tmpdir)
# ---------------------------------------------------------------------------


class TestGitHubDownloadProject:
    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_happy_path_returns_tuple(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()

        result = d.download_project("https://github.com/owner/repo.git", "scan-123")

        assert result is not None
        project_dir, parent_dir = result
        assert project_dir.name == "repo"
        assert project_dir.parent.name == "owner"

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_parent_dir_name_used_as_scan_namespace(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()

        _, parent_dir = d.download_project("https://github.com/owner/repo.git", "my-scan")

        assert parent_dir.name == "my-scan"

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_shallow_clone_by_default(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()
        d.download_project("https://github.com/owner/repo.git", "scan-123")

        args = mock_run.call_args[0][0]
        assert "--depth=1" in args

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_full_clone_when_requested(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()
        d.download_project("https://github.com/owner/repo.git", "scan-123", use_shallow_clone=False)

        args = mock_run.call_args[0][0]
        assert "--depth=1" not in args

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_subprocess_failure_returns_none(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git", stderr="error")
        d = GitHubProjectDownloader()

        result = d.download_project("https://github.com/owner/repo.git", "scan-123")

        assert result is None

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_invalid_url_returns_none(self, mock_run):
        d = GitHubProjectDownloader()

        result = d.download_project("https://bitbucket.org/owner/repo.git", "scan-123")

        assert result is None
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# GitHubProjectDownloader — download_to_permanent_location
# ---------------------------------------------------------------------------


class TestGitHubDownloadToPermanentLocation:
    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_happy_path_returns_path(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()

        result = d.download_to_permanent_location(
            "https://github.com/owner/repo.git",
            tmp_path,
        )

        assert result is not None
        assert result == tmp_path / "owner" / "repo"

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_flat_structure_uses_repo_name_only(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()

        result = d.download_to_permanent_location(
            "https://github.com/owner/repo.git",
            tmp_path,
            flat_structure=True,
        )

        assert result is not None
        assert result == tmp_path / "repo"

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_cwd_is_parent_dir(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()

        d.download_to_permanent_location("https://github.com/owner/repo.git", tmp_path)

        kwargs = mock_run.call_args[1]
        # cwd must be the parent of the final project directory
        cwd_path = Path(kwargs["cwd"])
        assert cwd_path == (tmp_path / "owner").resolve()

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_failure_returns_none(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git", stderr="error")
        d = GitHubProjectDownloader()

        result = d.download_to_permanent_location("https://github.com/owner/repo.git", tmp_path)

        assert result is None

    @patch("gsast_core.repolib.downloader.github_downloader.subprocess.run")
    def test_no_os_chdir_called(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitHubProjectDownloader()
        with patch("os.chdir") as mock_chdir:
            d.download_to_permanent_location("https://github.com/owner/repo.git", tmp_path)
            mock_chdir.assert_not_called()


# ---------------------------------------------------------------------------
# GitLabProjectDownloader — initialisation
# ---------------------------------------------------------------------------


class TestGitLabProjectDownloaderInit:
    def test_stores_scheme_and_host(self):
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        assert d.gitlab_scheme == "https"
        assert d.gitlab_host == "gitlab.example.com"

    def test_stores_token(self):
        d = GitLabProjectDownloader("https://gitlab.example.com", "secret")
        assert d.GITLAB_API_TOKEN == "secret"

    def test_temp_dir_is_created(self):
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        assert os.path.isdir(d.temp_dir)

    def test_git_lfs_env_set(self):
        GitLabProjectDownloader("https://gitlab.example.com", "tok")
        assert os.environ.get("GIT_LFS_SKIP_SMUDGE") == "1"

    def test_get_project_path_delegates_to_helper(self):
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        assert d.get_project_path("git@gitlab.example.com:group/repo.git") == PurePath("group/repo")


# ---------------------------------------------------------------------------
# GitLabProjectDownloader — _download_project subprocess args
# ---------------------------------------------------------------------------


class TestGitLabDownloadProjectSubprocess:
    def _make_result(self, stdout="", returncode=0):
        r = MagicMock()
        r.stdout = stdout
        r.returncode = returncode
        return r

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_shallow_clone_args(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        d._download_project(PurePath("group/repo"), Path("/tmp/dest"), use_shallow_clone=True)

        args = mock_run.call_args[0][0]
        assert "--depth=1" in args
        assert "--single-branch" in args

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_full_clone_omits_depth_flag(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        d._download_project(PurePath("group/repo"), Path("/tmp/dest"), use_shallow_clone=False)

        args = mock_run.call_args[0][0]
        assert "--depth=1" not in args

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_cwd_is_passed_not_chdir(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        dest = Path("/tmp/dest")
        d._download_project(PurePath("group/repo"), dest, use_shallow_clone=True)

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == str(dest)

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_no_os_chdir_called(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        with patch("os.chdir") as mock_chdir:
            d._download_project(PurePath("group/repo"), Path("/tmp/d"), use_shallow_clone=True)
            mock_chdir.assert_not_called()

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_download_url_contains_oauth2_token(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitLabProjectDownloader("https://gitlab.example.com", "secret-token")
        d._download_project(PurePath("group/repo"), Path("/tmp/d"), use_shallow_clone=True)

        args = mock_run.call_args[0][0]
        url_arg = args[-1]
        assert "oauth2:secret-token@gitlab.example.com" in url_arg

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_download_url_ends_with_dot_git(self, mock_run):
        mock_run.return_value = self._make_result()
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        d._download_project(PurePath("group/repo"), Path("/tmp/d"), use_shallow_clone=True)

        args = mock_run.call_args[0][0]
        url_arg = args[-1]
        assert url_arg.endswith("group/repo.git")

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_called_process_error_is_reraised(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git", stderr="fatal")
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        with pytest.raises(subprocess.CalledProcessError):
            d._download_project(PurePath("group/repo"), Path("/tmp/d"), use_shallow_clone=True)


# ---------------------------------------------------------------------------
# GitLabProjectDownloader — download_project (integration-style with real tmpdir)
# ---------------------------------------------------------------------------


class TestGitLabDownloadProject:
    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_happy_path_returns_tuple(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        result = d.download_project("git@gitlab.example.com:group/repo.git", "scan-456")

        assert result is not None
        project_dir, parent_dir = result
        assert project_dir.name == "repo"
        assert project_dir.parent.name == "group"

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_parent_dir_name_used_as_scan_namespace(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        _, parent_dir = d.download_project("git@gitlab.example.com:group/repo.git", "my-scan")

        assert parent_dir.name == "my-scan"

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_shallow_clone_by_default(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        d.download_project("git@gitlab.example.com:group/repo.git", "scan-456")

        args = mock_run.call_args[0][0]
        assert "--depth=1" in args

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_full_clone_when_requested(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        d.download_project("git@gitlab.example.com:group/repo.git", "scan-456", use_shallow_clone=False)

        args = mock_run.call_args[0][0]
        assert "--depth=1" not in args

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_subprocess_failure_returns_none(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git", stderr="error")
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        result = d.download_project("git@gitlab.example.com:group/repo.git", "scan-456")

        assert result is None

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_nested_namespace_project(self, mock_run):
        """Groups with sub-groups (a/b/repo) produce the correct nested directory structure."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        result = d.download_project("git@gitlab.example.com:a/b/repo.git", "scan-789")

        assert result is not None
        project_dir, _ = result
        assert project_dir.name == "repo"


# ---------------------------------------------------------------------------
# GitLabProjectDownloader — download_to_permanent_location
# ---------------------------------------------------------------------------


class TestGitLabDownloadToPermanentLocation:
    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_happy_path_returns_path(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        result = d.download_to_permanent_location(
            "git@gitlab.example.com:group/repo.git",
            tmp_path,
        )

        assert result is not None
        assert result == tmp_path / "group" / "repo"

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_flat_structure_uses_repo_name_only(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        result = d.download_to_permanent_location(
            "git@gitlab.example.com:group/repo.git",
            tmp_path,
            flat_structure=True,
        )

        assert result is not None
        assert result == tmp_path / "repo"

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_cwd_is_parent_dir(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        d.download_to_permanent_location("git@gitlab.example.com:group/repo.git", tmp_path)

        kwargs = mock_run.call_args[1]
        cwd_path = Path(kwargs["cwd"])
        assert cwd_path == (tmp_path / "group").resolve()

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_failure_returns_none(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.CalledProcessError(128, "git", stderr="error")
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")

        result = d.download_to_permanent_location("git@gitlab.example.com:group/repo.git", tmp_path)

        assert result is None

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_no_os_chdir_called(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "tok")
        with patch("os.chdir") as mock_chdir:
            d.download_to_permanent_location("git@gitlab.example.com:group/repo.git", tmp_path)
            mock_chdir.assert_not_called()

    @patch("gsast_core.repolib.downloader.gitlab_downloader.subprocess.run")
    def test_download_url_has_token(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        d = GitLabProjectDownloader("https://gitlab.example.com", "secret")

        d.download_to_permanent_location("git@gitlab.example.com:group/repo.git", tmp_path)

        args = mock_run.call_args[0][0]
        url_arg = next(a for a in args if "oauth2" in a)
        assert "oauth2:secret@gitlab.example.com" in url_arg
