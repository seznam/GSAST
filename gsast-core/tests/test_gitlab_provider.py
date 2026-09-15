"""
Tests for GitLabProvider.fetch_repositories memory-safe listing.

The production failure mode was:
- projects.list(all=True) materialised every GitLab project in RAM
- then projects.get(id, statistics=True) for each one
- four concurrent weekly scans OOMKilled the API pod (2.5Gi)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from gsast_core.repolib.gitlab_provider import GitLabProvider
from gsast_core.models.config_models import FiltersConfig, GitLabTargetConfig


def _project(**overrides):
    """A GitLab list-payload project: no `statistics` attribute unless provided."""
    attrs = dict(
        id=1,
        name='repo',
        path_with_namespace='group/repo',
        description='d',
        http_url_to_repo='https://gitlab.example/group/repo.git',
        ssh_url_to_repo='git@gitlab.example:group/repo.git',
        web_url='https://gitlab.example/group/repo',
        star_count=0,
        forks_count=0,
        archived=False,
        forked_from_project=None,
        last_activity_at='2024-06-01T00:00:00Z',
        created_at='2023-01-01T00:00:00Z',
        namespace={'kind': 'group', 'path': 'group'},
        visibility='private',
    )
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


def _provider():
    provider = GitLabProvider.__new__(GitLabProvider)
    provider.gitlab_url = 'https://gitlab.example'
    provider.GITLAB_API_TOKEN = 'token'
    provider.cache_backend = None
    provider.client = MagicMock()
    return provider


def _filters(**kwargs):
    defaults = dict(is_archived=False, is_fork=False, is_personal_project=False)
    defaults.update(kwargs)
    return FiltersConfig(**defaults)


class TestListCallShape:
    def test_instance_wide_list_streams_and_does_not_use_all_true(self):
        provider = _provider()
        provider.client.projects.list.return_value = [_project()]

        provider.fetch_repositories(GitLabTargetConfig(), _filters(), None)

        kwargs = provider.client.projects.list.call_args.kwargs
        assert kwargs.get('iterator') is True
        assert kwargs.get('all') not in (True,)
        assert kwargs.get('get_all') not in (True,)
        assert kwargs.get('per_page') == 100
        assert kwargs.get('pagination') == 'keyset'
        assert kwargs.get('order_by') == 'id'
        assert kwargs.get('with_shared') is True
        assert kwargs.get('archived') is False

    def test_does_not_get_each_project_when_size_filter_absent(self):
        provider = _provider()
        provider.client.projects.list.return_value = [
            _project(id=1),
            _project(id=2, name='r2', path_with_namespace='group/r2'),
        ]

        repos = provider.fetch_repositories(GitLabTargetConfig(), _filters(), None)

        provider.client.projects.get.assert_not_called()
        assert len(repos) == 2

    def test_gets_project_statistics_only_when_size_filter_set(self):
        provider = _provider()
        listed = _project(id=7)
        provider.client.projects.list.return_value = [listed]
        provider.client.projects.get.return_value = _project(
            id=7,
            statistics={'repository_size': 5 * 1024 * 1024},
        )

        repos = provider.fetch_repositories(
            GitLabTargetConfig(),
            _filters(max_repo_mb_size=50),
            None,
        )

        provider.client.projects.get.assert_called_once_with(7, statistics=True)
        assert len(repos) == 1
        assert repos[0].size_mb == 5

    def test_skips_get_when_list_payload_already_has_statistics(self):
        provider = _provider()
        provider.client.projects.list.return_value = [
            _project(id=3, statistics={'repository_size': 1024 * 1024}),
        ]

        repos = provider.fetch_repositories(
            GitLabTargetConfig(),
            _filters(max_repo_mb_size=50),
            None,
        )

        provider.client.projects.get.assert_not_called()
        assert repos[0].size_mb == 1

    def test_does_not_pass_archived_when_filter_unspecified(self):
        provider = _provider()
        provider.client.projects.list.return_value = [_project()]

        provider.fetch_repositories(GitLabTargetConfig(), None, None)

        kwargs = provider.client.projects.list.call_args.kwargs
        assert 'archived' not in kwargs

    def test_keyset_failure_falls_back_to_offset_pagination(self):
        provider = _provider()
        provider.client.projects.list.side_effect = [
            RuntimeError('keyset unsupported'),
            [_project()],
        ]

        repos = provider.fetch_repositories(GitLabTargetConfig(), _filters(), None)

        assert len(repos) == 1
        assert provider.client.projects.list.call_count == 2
        fallback_kwargs = provider.client.projects.list.call_args_list[1].kwargs
        assert fallback_kwargs.get('pagination') != 'keyset'
        assert fallback_kwargs.get('iterator') is True


class TestTargetSelection:
    def test_group_listing_does_not_fall_back_to_instance_wide(self):
        provider = _provider()
        group = MagicMock()
        group.projects.list.return_value = [_project()]
        provider.client.groups.get.return_value = group

        repos = provider.fetch_repositories(
            GitLabTargetConfig(groups=['mygroup']),
            _filters(),
            None,
        )

        provider.client.groups.get.assert_called_once_with('mygroup')
        provider.client.projects.list.assert_not_called()
        group_kwargs = group.projects.list.call_args.kwargs
        assert group_kwargs.get('include_subgroups') is True
        assert group_kwargs.get('iterator') is True
        assert len(repos) == 1

    def test_empty_group_does_not_scan_the_whole_instance(self):
        provider = _provider()
        group = MagicMock()
        group.projects.list.return_value = []
        provider.client.groups.get.return_value = group

        repos = provider.fetch_repositories(
            GitLabTargetConfig(groups=['empty-group']),
            _filters(),
            None,
        )

        assert repos == []
        provider.client.projects.list.assert_not_called()

    def test_specific_repository_uses_get_not_list(self):
        provider = _provider()
        provider.client.projects.get.return_value = _project(
            path_with_namespace='group/named',
            name='named',
        )

        repos = provider.fetch_repositories(
            GitLabTargetConfig(repositories=['group/named']),
            _filters(),
            None,
        )

        provider.client.projects.list.assert_not_called()
        provider.client.projects.get.assert_called_once_with('group/named')
        assert repos[0].full_name == 'group/named'


class TestConversionAndFilters:
    def test_personal_and_fork_projects_are_filtered_out(self):
        provider = _provider()
        provider.client.projects.list.return_value = [
            _project(id=1, path_with_namespace='group/ok', name='ok'),
            _project(
                id=2,
                name='fork',
                path_with_namespace='user/fork',
                forked_from_project={'id': 99},
                namespace={'kind': 'user', 'path': 'user'},
            ),
            _project(
                id=3,
                name='personal',
                path_with_namespace='user/personal',
                namespace={'kind': 'user', 'path': 'user'},
            ),
            _project(id=4, name='archived', path_with_namespace='group/arch', archived=True),
        ]

        repos = provider.fetch_repositories(GitLabTargetConfig(), _filters(), None)

        assert [r.full_name for r in repos] == ['group/ok']

    def test_namespace_rest_object_without_dict_get(self):
        provider = _provider()
        ns = SimpleNamespace(kind='user', path='jane')
        repo = provider._convert_gitlab_project(
            _project(namespace=ns, path_with_namespace='jane/repo')
        )
        assert repo.is_personal_project is True
        assert repo.owner == 'jane'

    def test_is_fork_from_list_payload_without_extra_get(self):
        provider = _provider()
        repo = provider._convert_gitlab_project(
            _project(forked_from_project={'id': 1, 'path_with_namespace': 'origin/repo'})
        )
        assert repo.is_fork is True

    def test_fetch_errors_are_raised_not_swallowed_as_empty(self):
        provider = _provider()
        provider.client.projects.list.side_effect = RuntimeError('gitlab 502')

        with pytest.raises(RuntimeError, match='gitlab 502'):
            provider.fetch_repositories(GitLabTargetConfig(), _filters(), None)


class TestStatusCallback:
    def test_status_updater_receives_progress_without_requiring_total(self):
        provider = _provider()
        provider.client.projects.list.return_value = [_project()]
        updater = Mock()

        provider.fetch_repositories(GitLabTargetConfig(), _filters(), updater)

        messages = [c.args[0] for c in updater.update_callback.call_args_list]
        assert messages
        assert all('/' not in m.split('processed')[0] or 'processed' in m for m in messages)
        assert '1 processed' in messages[-1]
        assert '1 matched' in messages[-1]
