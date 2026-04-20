"""
Tests for the shared filter_repository() function in repolib/filters.py.

Covers every filter condition:
- None filters  → always passes
- is_archived
- is_fork
- is_personal_project
- max_repo_mb_size
- last_commit_max_age
- ignore_path_regexes
- must_path_regexes
- Multiple active filters (AND semantics)
"""

import pytest
from datetime import datetime, timedelta, timezone

from repolib.base import BaseRepository
from repolib.filters import filter_repository
from models.config_models import FiltersConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo(**overrides) -> BaseRepository:
    """Return a BaseRepository that passes every default filter."""
    defaults = dict(
        name="my-repo",
        full_name="org/my-repo",
        archived=False,
        is_fork=False,
        is_personal_project=False,
        size_mb=10,
        last_activity=datetime.now(timezone.utc) - timedelta(days=5),
    )
    defaults.update(overrides)
    return BaseRepository(**defaults)


# ---------------------------------------------------------------------------
# None / empty filters
# ---------------------------------------------------------------------------

class TestNoFilters:
    def test_none_filters_always_passes(self):
        assert filter_repository(None, _repo()) is True

    def test_empty_filters_always_passes(self):
        assert filter_repository(FiltersConfig(), _repo()) is True

    def test_none_filters_passes_archived_repo(self):
        assert filter_repository(None, _repo(archived=True)) is True

    def test_none_filters_passes_fork(self):
        assert filter_repository(None, _repo(is_fork=True)) is True


# ---------------------------------------------------------------------------
# is_archived
# ---------------------------------------------------------------------------

class TestIsArchivedFilter:
    def test_keep_non_archived_passes_when_filter_false(self):
        assert filter_repository(FiltersConfig(is_archived=False), _repo(archived=False)) is True

    def test_archived_fails_when_filter_false(self):
        assert filter_repository(FiltersConfig(is_archived=False), _repo(archived=True)) is False

    def test_keep_archived_passes_when_filter_true(self):
        assert filter_repository(FiltersConfig(is_archived=True), _repo(archived=True)) is True

    def test_non_archived_fails_when_filter_true(self):
        assert filter_repository(FiltersConfig(is_archived=True), _repo(archived=False)) is False

    def test_none_is_archived_ignores_archived_flag(self):
        assert filter_repository(FiltersConfig(is_archived=None), _repo(archived=True)) is True
        assert filter_repository(FiltersConfig(is_archived=None), _repo(archived=False)) is True


# ---------------------------------------------------------------------------
# is_fork
# ---------------------------------------------------------------------------

class TestIsForkFilter:
    def test_non_fork_passes_when_filter_false(self):
        assert filter_repository(FiltersConfig(is_fork=False), _repo(is_fork=False)) is True

    def test_fork_fails_when_filter_false(self):
        assert filter_repository(FiltersConfig(is_fork=False), _repo(is_fork=True)) is False

    def test_fork_passes_when_filter_true(self):
        assert filter_repository(FiltersConfig(is_fork=True), _repo(is_fork=True)) is True

    def test_non_fork_fails_when_filter_true(self):
        assert filter_repository(FiltersConfig(is_fork=True), _repo(is_fork=False)) is False

    def test_none_is_fork_ignores_fork_flag(self):
        assert filter_repository(FiltersConfig(is_fork=None), _repo(is_fork=True)) is True
        assert filter_repository(FiltersConfig(is_fork=None), _repo(is_fork=False)) is True


# ---------------------------------------------------------------------------
# is_personal_project
# ---------------------------------------------------------------------------

class TestIsPersonalProjectFilter:
    def test_personal_project_passes_when_filter_true(self):
        f = FiltersConfig(is_personal_project=True)
        assert filter_repository(f, _repo(is_personal_project=True)) is True

    def test_non_personal_fails_when_filter_true(self):
        f = FiltersConfig(is_personal_project=True)
        assert filter_repository(f, _repo(is_personal_project=False)) is False

    def test_non_personal_passes_when_filter_false(self):
        f = FiltersConfig(is_personal_project=False)
        assert filter_repository(f, _repo(is_personal_project=False)) is True

    def test_personal_fails_when_filter_false(self):
        f = FiltersConfig(is_personal_project=False)
        assert filter_repository(f, _repo(is_personal_project=True)) is False

    def test_none_ignores_personal_project_flag(self):
        f = FiltersConfig(is_personal_project=None)
        assert filter_repository(f, _repo(is_personal_project=True)) is True
        assert filter_repository(f, _repo(is_personal_project=False)) is True


# ---------------------------------------------------------------------------
# max_repo_mb_size
# ---------------------------------------------------------------------------

class TestMaxRepoMbSizeFilter:
    def test_repo_within_limit_passes(self):
        f = FiltersConfig(max_repo_mb_size=100)
        assert filter_repository(f, _repo(size_mb=50)) is True

    def test_repo_at_limit_passes(self):
        f = FiltersConfig(max_repo_mb_size=100)
        assert filter_repository(f, _repo(size_mb=100)) is True

    def test_repo_over_limit_fails(self):
        f = FiltersConfig(max_repo_mb_size=100)
        assert filter_repository(f, _repo(size_mb=101)) is False

    def test_zero_size_always_passes(self):
        f = FiltersConfig(max_repo_mb_size=0)
        assert filter_repository(f, _repo(size_mb=0)) is True

    def test_zero_size_repo_over_zero_limit_fails(self):
        f = FiltersConfig(max_repo_mb_size=0)
        assert filter_repository(f, _repo(size_mb=1)) is False

    def test_none_max_size_ignores_size(self):
        f = FiltersConfig(max_repo_mb_size=None)
        assert filter_repository(f, _repo(size_mb=10_000)) is True


# ---------------------------------------------------------------------------
# last_commit_max_age
# ---------------------------------------------------------------------------

class TestLastCommitMaxAgeFilter:
    def test_recent_activity_passes(self):
        f = FiltersConfig(last_commit_max_age=30)
        repo = _repo(last_activity=datetime.now(timezone.utc) - timedelta(days=10))
        assert filter_repository(f, repo) is True

    def test_activity_at_exact_limit_passes(self):
        f = FiltersConfig(last_commit_max_age=30)
        repo = _repo(last_activity=datetime.now(timezone.utc) - timedelta(days=30))
        assert filter_repository(f, repo) is True

    def test_stale_activity_fails(self):
        f = FiltersConfig(last_commit_max_age=30)
        repo = _repo(last_activity=datetime.now(timezone.utc) - timedelta(days=31))
        assert filter_repository(f, repo) is False

    def test_none_last_activity_is_not_filtered_out(self):
        """When last_activity is None the age check should be skipped."""
        f = FiltersConfig(last_commit_max_age=1)
        repo = _repo(last_activity=None)
        assert filter_repository(f, repo) is True

    def test_none_max_age_ignores_last_activity(self):
        f = FiltersConfig(last_commit_max_age=None)
        repo = _repo(last_activity=datetime.now(timezone.utc) - timedelta(days=3650))
        assert filter_repository(f, repo) is True

    def test_zero_max_age_passes_for_today(self):
        f = FiltersConfig(last_commit_max_age=0)
        repo = _repo(last_activity=datetime.now(timezone.utc))
        assert filter_repository(f, repo) is True


# ---------------------------------------------------------------------------
# ignore_path_regexes
# ---------------------------------------------------------------------------

class TestIgnorePathRegexesFilter:
    def test_matching_pattern_excludes_repo(self):
        f = FiltersConfig(ignore_path_regexes=[r"org/my-repo"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is False

    def test_non_matching_pattern_keeps_repo(self):
        f = FiltersConfig(ignore_path_regexes=[r"org/other"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True

    def test_any_pattern_matching_excludes_repo(self):
        f = FiltersConfig(ignore_path_regexes=[r"irrelevant", r"my-repo"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is False

    def test_no_patterns_matching_keeps_repo(self):
        f = FiltersConfig(ignore_path_regexes=[r"alpha", r"beta"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True

    def test_regex_special_chars_work(self):
        f = FiltersConfig(ignore_path_regexes=[r"^org/.*"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is False
        assert filter_repository(f, _repo(full_name="other/my-repo")) is True

    def test_none_ignore_regexes_never_filters(self):
        f = FiltersConfig(ignore_path_regexes=None)
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True

    def test_empty_ignore_list_never_filters(self):
        f = FiltersConfig(ignore_path_regexes=[])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True

    def test_pattern_matches_substring(self):
        f = FiltersConfig(ignore_path_regexes=[r"fork"])
        assert filter_repository(f, _repo(full_name="org/forked-thing")) is False
        assert filter_repository(f, _repo(full_name="org/main-thing")) is True


# ---------------------------------------------------------------------------
# must_path_regexes
# ---------------------------------------------------------------------------

class TestMustPathRegexesFilter:
    def test_matching_pattern_keeps_repo(self):
        f = FiltersConfig(must_path_regexes=[r"org/my-repo"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True

    def test_non_matching_pattern_excludes_repo(self):
        f = FiltersConfig(must_path_regexes=[r"org/other"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is False

    def test_at_least_one_pattern_matching_keeps_repo(self):
        f = FiltersConfig(must_path_regexes=[r"irrelevant", r"my-repo"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True

    def test_none_of_several_patterns_matching_excludes_repo(self):
        f = FiltersConfig(must_path_regexes=[r"alpha", r"beta"])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is False

    def test_regex_anchored_pattern(self):
        f = FiltersConfig(must_path_regexes=[r"^myorg/"])
        assert filter_repository(f, _repo(full_name="myorg/cool-repo")) is True
        assert filter_repository(f, _repo(full_name="other/cool-repo")) is False

    def test_none_must_regexes_never_filters(self):
        f = FiltersConfig(must_path_regexes=None)
        assert filter_repository(f, _repo(full_name="totally-unrelated")) is True

    def test_empty_must_list_never_filters(self):
        f = FiltersConfig(must_path_regexes=[])
        assert filter_repository(f, _repo(full_name="org/my-repo")) is True


# ---------------------------------------------------------------------------
# ignore + must interaction
# ---------------------------------------------------------------------------

class TestIgnoreAndMustInteraction:
    def test_ignore_wins_when_both_match(self):
        """A repo matching both ignore and must is excluded (ignore applied first)."""
        f = FiltersConfig(
            ignore_path_regexes=[r"my-repo"],
            must_path_regexes=[r"my-repo"],
        )
        assert filter_repository(f, _repo(full_name="org/my-repo")) is False

    def test_must_filters_when_ignore_doesnt_match(self):
        f = FiltersConfig(
            ignore_path_regexes=[r"archived"],
            must_path_regexes=[r"^org/"],
        )
        assert filter_repository(f, _repo(full_name="org/cool-repo")) is True
        assert filter_repository(f, _repo(full_name="personal/cool-repo")) is False


# ---------------------------------------------------------------------------
# Multiple filters combined (AND semantics)
# ---------------------------------------------------------------------------

class TestMultipleFilters:
    def test_all_conditions_pass(self):
        f = FiltersConfig(
            is_archived=False,
            is_fork=False,
            max_repo_mb_size=100,
            last_commit_max_age=60,
            must_path_regexes=[r"^org/"],
        )
        repo = _repo(
            full_name="org/good-repo",
            archived=False,
            is_fork=False,
            size_mb=50,
            last_activity=datetime.now(timezone.utc) - timedelta(days=10),
        )
        assert filter_repository(f, repo) is True

    def test_one_failing_condition_excludes_repo(self):
        f = FiltersConfig(
            is_archived=False,
            is_fork=False,
            max_repo_mb_size=100,
        )
        repo = _repo(archived=False, is_fork=True, size_mb=50)
        assert filter_repository(f, repo) is False

    def test_size_violation_with_other_conditions_passing_excludes_repo(self):
        f = FiltersConfig(
            is_archived=False,
            max_repo_mb_size=10,
        )
        repo = _repo(archived=False, size_mb=50)
        assert filter_repository(f, repo) is False
