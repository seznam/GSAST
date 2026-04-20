"""
Tests for BaseRepository serialization.

Covers:
- to_dict() produces the correct dictionary representation
- from_dict() deserializes a dictionary back to a BaseRepository
- Round-trip fidelity (to_dict → from_dict produces an equivalent object)
- Datetime serialization: isoformat strings in to_dict, datetime objects in from_dict
- None datetime fields remain None through the round-trip
- Default field values when constructed with no arguments
"""

import pytest
from datetime import datetime, timezone

from gsast_core.repolib.base import BaseRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_repo(**overrides) -> BaseRepository:
    """Return a fully-populated BaseRepository, optionally with overrides."""
    defaults = dict(
        name="my-repo",
        full_name="org/my-repo",
        description="A test repository",
        clone_url="https://github.com/org/my-repo.git",
        ssh_url="git@github.com:org/my-repo.git",
        web_url="https://github.com/org/my-repo",
        size_mb=42,
        stars=7,
        forks=3,
        language="Python",
        archived=False,
        is_fork=True,
        is_personal_project=False,
        last_activity=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        owner="org",
        private=True,
    )
    defaults.update(overrides)
    return BaseRepository(**defaults)


# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------

class TestBaseRepositoryDefaults:
    def test_default_string_fields_are_empty(self):
        repo = BaseRepository()
        for field in ("name", "full_name", "description", "clone_url",
                      "ssh_url", "web_url", "language", "owner"):
            assert getattr(repo, field) == "", f"Expected '' for {field}"

    def test_default_numeric_fields_are_zero(self):
        repo = BaseRepository()
        assert repo.size_mb == 0
        assert repo.stars == 0
        assert repo.forks == 0

    def test_default_boolean_fields_are_false(self):
        repo = BaseRepository()
        assert repo.archived is False
        assert repo.is_fork is False
        assert repo.is_personal_project is False
        assert repo.private is False

    def test_default_datetime_fields_are_none(self):
        repo = BaseRepository()
        assert repo.last_activity is None
        assert repo.created_at is None


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------

class TestToDict:
    def test_all_fields_present(self):
        repo = _full_repo()
        d = repo.to_dict()
        expected_keys = {
            "name", "full_name", "description", "clone_url", "ssh_url",
            "web_url", "size_mb", "stars", "forks", "language", "archived",
            "is_fork", "is_personal_project", "last_activity", "created_at",
            "owner", "private",
        }
        assert set(d.keys()) == expected_keys

    def test_scalar_fields_match(self):
        repo = _full_repo()
        d = repo.to_dict()
        assert d["name"] == "my-repo"
        assert d["full_name"] == "org/my-repo"
        assert d["description"] == "A test repository"
        assert d["clone_url"] == "https://github.com/org/my-repo.git"
        assert d["ssh_url"] == "git@github.com:org/my-repo.git"
        assert d["web_url"] == "https://github.com/org/my-repo"
        assert d["size_mb"] == 42
        assert d["stars"] == 7
        assert d["forks"] == 3
        assert d["language"] == "Python"
        assert d["archived"] is False
        assert d["is_fork"] is True
        assert d["is_personal_project"] is False
        assert d["owner"] == "org"
        assert d["private"] is True

    def test_last_activity_serialized_as_isoformat(self):
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        repo = _full_repo(last_activity=dt)
        assert repo.to_dict()["last_activity"] == dt.isoformat()

    def test_created_at_serialized_as_isoformat(self):
        dt = datetime(2021, 1, 1, tzinfo=timezone.utc)
        repo = _full_repo(created_at=dt)
        assert repo.to_dict()["created_at"] == dt.isoformat()

    def test_none_last_activity_serializes_to_none(self):
        repo = _full_repo(last_activity=None)
        assert repo.to_dict()["last_activity"] is None

    def test_none_created_at_serializes_to_none(self):
        repo = _full_repo(created_at=None)
        assert repo.to_dict()["created_at"] is None

    def test_datetime_value_is_string_not_datetime(self):
        repo = _full_repo()
        d = repo.to_dict()
        assert isinstance(d["last_activity"], str)
        assert isinstance(d["created_at"], str)

    def test_default_repo_to_dict_has_none_datetimes(self):
        repo = BaseRepository()
        d = repo.to_dict()
        assert d["last_activity"] is None
        assert d["created_at"] is None


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------

class TestFromDict:
    def test_returns_base_repository_instance(self):
        d = _full_repo().to_dict()
        result = BaseRepository.from_dict(d)
        assert isinstance(result, BaseRepository)

    def test_scalar_fields_restored(self):
        original = _full_repo()
        restored = BaseRepository.from_dict(original.to_dict())
        for field in ("name", "full_name", "description", "clone_url",
                      "ssh_url", "web_url", "size_mb", "stars", "forks",
                      "language", "archived", "is_fork", "is_personal_project",
                      "owner", "private"):
            assert getattr(restored, field) == getattr(original, field), \
                f"Mismatch for field {field!r}"

    def test_iso_string_last_activity_parsed_to_datetime(self):
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        d = {"last_activity": dt.isoformat(), "created_at": None}
        repo = BaseRepository.from_dict(d)
        assert repo.last_activity == dt
        assert isinstance(repo.last_activity, datetime)

    def test_iso_string_created_at_parsed_to_datetime(self):
        dt = datetime(2021, 1, 1, tzinfo=timezone.utc)
        d = {"created_at": dt.isoformat(), "last_activity": None}
        repo = BaseRepository.from_dict(d)
        assert repo.created_at == dt
        assert isinstance(repo.created_at, datetime)

    def test_none_last_activity_stays_none(self):
        d = {"last_activity": None, "created_at": None}
        repo = BaseRepository.from_dict(d)
        assert repo.last_activity is None

    def test_none_created_at_stays_none(self):
        d = {"last_activity": None, "created_at": None}
        repo = BaseRepository.from_dict(d)
        assert repo.created_at is None

    def test_from_dict_with_no_datetime_keys(self):
        """from_dict must not crash when datetime keys are absent."""
        repo = BaseRepository.from_dict({"name": "x"})
        assert repo.name == "x"
        assert repo.last_activity is None
        assert repo.created_at is None

    def test_from_dict_does_not_mutate_input(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        d = {"last_activity": dt.isoformat(), "created_at": None}
        original_d = dict(d)
        BaseRepository.from_dict(d)
        assert d == original_d


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def _assert_equal(self, a: BaseRepository, b: BaseRepository):
        for field in ("name", "full_name", "description", "clone_url",
                      "ssh_url", "web_url", "size_mb", "stars", "forks",
                      "language", "archived", "is_fork", "is_personal_project",
                      "last_activity", "created_at", "owner", "private"):
            assert getattr(a, field) == getattr(b, field), \
                f"Round-trip mismatch for field {field!r}"

    def test_full_repo_round_trip(self):
        original = _full_repo()
        restored = BaseRepository.from_dict(original.to_dict())
        self._assert_equal(original, restored)

    def test_default_repo_round_trip(self):
        original = BaseRepository()
        restored = BaseRepository.from_dict(original.to_dict())
        self._assert_equal(original, restored)

    def test_repo_with_no_datetime_round_trip(self):
        original = _full_repo(last_activity=None, created_at=None)
        restored = BaseRepository.from_dict(original.to_dict())
        self._assert_equal(original, restored)

    def test_naive_datetime_round_trip(self):
        """Naive datetimes (no tzinfo) should survive the round-trip unchanged."""
        naive_dt = datetime(2023, 3, 14, 9, 26, 53)
        original = _full_repo(last_activity=naive_dt, created_at=naive_dt)
        restored = BaseRepository.from_dict(original.to_dict())
        assert restored.last_activity == naive_dt
        assert restored.created_at == naive_dt

    def test_double_round_trip_is_stable(self):
        """Serializing and deserializing twice should yield identical results."""
        original = _full_repo()
        once = BaseRepository.from_dict(original.to_dict())
        twice = BaseRepository.from_dict(once.to_dict())
        self._assert_equal(once, twice)

    def test_all_boolean_combinations_round_trip(self):
        for archived in (True, False):
            for is_fork in (True, False):
                for private in (True, False):
                    repo = _full_repo(archived=archived, is_fork=is_fork, private=private)
                    restored = BaseRepository.from_dict(repo.to_dict())
                    assert restored.archived is archived
                    assert restored.is_fork is is_fork
                    assert restored.private is private

    def test_to_dict_returns_plain_dict(self):
        """to_dict output must be a plain dict (JSON-serialisable values)."""
        import json
        repo = _full_repo()
        d = repo.to_dict()
        # Should not raise
        json.dumps(d)
