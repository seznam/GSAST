"""
Comprehensive tests for UnifiedRepositoryAPI.

This test suite verifies all aspects of the UnifiedRepositoryAPI including:
- Provider initialization for GitHub and GitLab
- Repository fetching functionality
- URL retrieval methods
- Repository downloading
- Error handling and edge cases
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from repolib.api import UnifiedRepositoryAPI
from repolib.base import BaseRepository
from repolib.status_updater import ProjectFetchStatusUpdater
from models.config_models import (
    TargetConfig,
    FiltersConfig,
    GitHubTargetConfig,
    GitLabTargetConfig,
    ProviderType
)


class TestUnifiedRepositoryAPIInitialization:
    """Test UnifiedRepositoryAPI initialization."""

    def test_github_provider_initialization_success(self):
        """Test successful GitHub provider initialization."""
        target = GitHubTargetConfig(organizations=['test-org'])
        filters = FiltersConfig(is_archived=False)
        
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_GITHUB_API_TOKEN'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider_instance = Mock()
                mock_github_provider.return_value = mock_provider_instance
                
                api = UnifiedRepositoryAPI(filters=filters, target=target, cache_backend='test_cache')
                
                # Verify initialization
                assert api.target == target
                assert api.filters == filters
                assert api.cache_backend == 'test_cache'
                assert api.provider == mock_provider_instance
                assert api._repositories == []
                
                # Verify provider was initialized correctly
                mock_github_provider.assert_called_once_with('test_GITHUB_API_TOKEN', 'test_cache')

    def test_gitlab_provider_initialization_success(self):
        """Test successful GitLab provider initialization."""
        target = GitLabTargetConfig(groups=['test-group'])
        filters = FiltersConfig(is_fork=False)
        
        with patch('repolib.api.GITLAB_API_TOKEN', 'test_GITLAB_API_TOKEN'):
            with patch('repolib.api.GITLAB_URL', 'https://gitlab.example.com'):
                with patch('repolib.api.GitLabProvider') as mock_gitlab_provider:
                    mock_provider_instance = Mock()
                    mock_gitlab_provider.return_value = mock_provider_instance
                    
                    api = UnifiedRepositoryAPI(filters=filters, target=target)
                    
                    # Verify initialization
                    assert api.target == target
                    assert api.filters == filters
                    assert api.provider == mock_provider_instance
                    
                    # Verify provider was initialized correctly
                    mock_gitlab_provider.assert_called_once_with('https://gitlab.example.com', 'test_GITLAB_API_TOKEN', None)

    def test_github_provider_missing_token_error(self):
        """Test error when GitHub token is missing."""
        target = GitHubTargetConfig(organizations=['test-org'])
        filters = FiltersConfig()
        
        with patch('repolib.api.GITHUB_API_TOKEN', None):
            with pytest.raises(ValueError, match="GitHub provider requires GITHUB_API_TOKEN environment variable"):
                UnifiedRepositoryAPI(filters=filters, target=target)

    def test_gitlab_provider_missing_token_error(self):
        """Test error when GitLab token is missing."""
        target = GitLabTargetConfig(groups=['test-group'])
        filters = FiltersConfig()
        
        with patch('repolib.api.GITLAB_API_TOKEN', None):
            with pytest.raises(ValueError, match="GitLab provider requires GITLAB_API_TOKEN environment variable"):
                UnifiedRepositoryAPI(filters=filters, target=target)

    def test_github_provider_initialization_failure(self):
        """Test error handling when GitHub provider initialization fails."""
        target = GitHubTargetConfig(organizations=['test-org'])
        filters = FiltersConfig()
        
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_github_provider.side_effect = Exception("Authentication failed")
                
                with pytest.raises(ValueError, match="Failed to initialize GitHub provider: Authentication failed"):
                    UnifiedRepositoryAPI(filters=filters, target=target)

    def test_gitlab_provider_initialization_failure(self):
        """Test error handling when GitLab provider initialization fails."""
        target = GitLabTargetConfig(groups=['test-group'])
        filters = FiltersConfig()
        
        with patch('repolib.api.GITLAB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GITLAB_URL', 'https://gitlab.com'):
                with patch('repolib.api.GitLabProvider') as mock_gitlab_provider:
                    mock_gitlab_provider.side_effect = Exception("Connection failed")
                    
                    with pytest.raises(ValueError, match="Failed to initialize GitLab provider: Connection failed"):
                        UnifiedRepositoryAPI(filters=filters, target=target)

    def test_unsupported_provider_error(self):
        """Test error when unsupported provider is used."""
        # Create a mock target with unsupported provider
        target = Mock()
        target.provider = "unsupported_provider"
        filters = FiltersConfig()
        
        with pytest.raises(ValueError, match="Unsupported provider: unsupported_provider"):
            UnifiedRepositoryAPI(filters=filters, target=target)


class TestUnifiedRepositoryAPIFetchRepositories:
    """Test fetch_repositories method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.target = GitHubTargetConfig(organizations=['test-org'])
        self.filters = FiltersConfig(is_archived=False)
        self.mock_repos = [
            BaseRepository(name='repo1', full_name='test-org/repo1', ssh_url='git@github.com:test-org/repo1.git'),
            BaseRepository(name='repo2', full_name='test-org/repo2', ssh_url='git@github.com:test-org/repo2.git'),
            BaseRepository(name='repo3', full_name='test-org/repo3', ssh_url='git@github.com:test-org/repo3.git')
        ]

    def test_fetch_repositories_returns_count(self):
        """Test that fetch_repositories returns the correct count."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.fetch_repositories.return_value = self.mock_repos
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                
                # Create mock status updater
                mock_status_updater = Mock(spec=ProjectFetchStatusUpdater)
                
                # Test fetch_repositories
                count = api.fetch_repositories(mock_status_updater)
                
                # Verify return value is count
                assert count == 3
                assert isinstance(count, int)

    def test_fetch_repositories_stores_repositories(self):
        """Test that fetch_repositories stores repositories internally."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.fetch_repositories.return_value = self.mock_repos
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                mock_status_updater = Mock(spec=ProjectFetchStatusUpdater)
                
                # Test fetch_repositories
                api.fetch_repositories(mock_status_updater)
                
                # Verify repositories are stored internally
                assert api._repositories == self.mock_repos

    def test_fetch_repositories_calls_provider_correctly(self):
        """Test that fetch_repositories calls provider with correct parameters."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.fetch_repositories.return_value = self.mock_repos
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                mock_status_updater = Mock(spec=ProjectFetchStatusUpdater)
                
                # Test fetch_repositories
                api.fetch_repositories(mock_status_updater)
                
                # Verify provider method was called correctly
                mock_provider.fetch_repositories.assert_called_once_with(
                    self.target, self.filters, mock_status_updater
                )

    def test_fetch_repositories_empty_result(self):
        """Test fetch_repositories with empty result."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.fetch_repositories.return_value = []
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                mock_status_updater = Mock(spec=ProjectFetchStatusUpdater)
                
                # Test fetch_repositories
                count = api.fetch_repositories(mock_status_updater)
                
                # Verify empty result
                assert count == 0
                assert api._repositories == []


class TestUnifiedRepositoryAPIGetRepositoriesUrls:
    """Test get_repositories_urls method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.target = GitHubTargetConfig(organizations=['test-org'])
        self.filters = FiltersConfig()
        self.mock_repos = [
            BaseRepository(name='repo1', 
                          ssh_url='git@github.com:test-org/repo1.git',
                          clone_url='https://github.com/test-org/repo1.git'),
            BaseRepository(name='repo2', 
                          ssh_url='git@github.com:test-org/repo2.git',
                          clone_url='https://github.com/test-org/repo2.git')
        ]
        self.expected_urls = ['https://github.com/test-org/repo1.git', 'https://github.com/test-org/repo2.git']  # These are clone URLs, not SSH URLs

    def test_get_repositories_urls_returns_correct_urls(self):
        """Test that get_repositories_urls returns correct URLs."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider'):
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                api._repositories = self.mock_repos  # Set repositories directly
                
                # Test get_repositories_urls
                urls = api.get_repositories_urls()
                
                # Verify return value
                assert urls == self.expected_urls
                assert isinstance(urls, list)

    def test_get_repositories_ssh_urls_calls_provider_correctly(self):
        """Test that get_repositories_ssh_urls calls provider with stored repositories."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                ssh_urls = ['git@github.com:test-org/repo1.git', 'git@github.com:test-org/repo2.git']
                mock_provider.get_repositories_ssh_urls.return_value = ssh_urls
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                api._repositories = self.mock_repos  # Set repositories directly
                
                # Test get_repositories_ssh_urls
                result_urls = api.get_repositories_ssh_urls()
                
                # Verify provider method was called with stored repositories
                mock_provider.get_repositories_ssh_urls.assert_called_once_with(self.mock_repos)
                assert result_urls == ssh_urls

    def test_get_repositories_urls_with_no_repositories(self):
        """Test get_repositories_urls when no repositories are stored."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                # _repositories is already empty by default
                
                # Test get_repositories_urls
                urls = api.get_repositories_urls()
                
                # Verify empty result
                assert urls == []

    def test_get_repositories_urls_no_parameters_required(self):
        """Test that get_repositories_urls takes no parameters (as required by tracked_scan.py)."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider'):
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                api._repositories = self.mock_repos
                
                # Test that method can be called without parameters
                urls = api.get_repositories_urls()  # No parameters
                
                assert urls == self.expected_urls


class TestUnifiedRepositoryAPIGetProviderType:
    """Test get_provider_type method."""

    def test_get_provider_type_github(self):
        """Test get_provider_type returns GitHub provider type."""
        target = GitHubTargetConfig(organizations=['test-org'])
        filters = FiltersConfig()
        
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider'):
                api = UnifiedRepositoryAPI(filters=filters, target=target)
                
                provider_type = api.get_provider_type()
                
                assert provider_type == ProviderType.GITHUB

    def test_get_provider_type_gitlab(self):
        """Test get_provider_type returns GitLab provider type."""
        target = GitLabTargetConfig(groups=['test-group'])
        filters = FiltersConfig()
        
        with patch('repolib.api.GITLAB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GITLAB_URL', 'https://gitlab.com'):
                with patch('repolib.api.GitLabProvider'):
                    api = UnifiedRepositoryAPI(filters=filters, target=target)
                    
                    provider_type = api.get_provider_type()
                    
                    assert provider_type == ProviderType.GITLAB


class TestUnifiedRepositoryAPIDownloadRepository:
    """Test download_repository method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.target = GitHubTargetConfig(repositories=['test-org/test-repo'])
        self.filters = FiltersConfig()
        self.test_repo = BaseRepository(
            name='test-repo',
            full_name='test-org/test-repo',
            clone_url='https://github.com/test-org/test-repo.git'
        )
        self.test_destination = Path('/tmp/test-destination')

    def test_download_repository_success(self):
        """Test successful repository download."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.download_repository.return_value = True
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                
                # Test download_repository
                result = api.download_repository(self.test_repo, self.test_destination, shallow=True)
                
                # Verify return value
                assert result is True
                assert isinstance(result, bool)

    def test_download_repository_failure(self):
        """Test repository download failure."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.download_repository.return_value = False
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                
                # Test download_repository
                result = api.download_repository(self.test_repo, self.test_destination, shallow=False)
                
                # Verify return value
                assert result is False

    def test_download_repository_calls_provider_correctly(self):
        """Test that download_repository calls provider with correct parameters."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.download_repository.return_value = True
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                
                # Test download_repository with custom parameters
                api.download_repository(self.test_repo, self.test_destination, shallow=False)
                
                # Verify provider method was called correctly
                mock_provider.download_repository.assert_called_once_with(
                    self.test_repo, self.test_destination, False
                )

    def test_download_repository_default_shallow_parameter(self):
        """Test that download_repository uses default shallow=True parameter."""
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.download_repository.return_value = True
                mock_github_provider.return_value = mock_provider
                
                api = UnifiedRepositoryAPI(filters=self.filters, target=self.target)
                
                # Test download_repository without shallow parameter
                api.download_repository(self.test_repo, self.test_destination)
                
                # Verify provider method was called with default shallow=True
                mock_provider.download_repository.assert_called_once_with(
                    self.test_repo, self.test_destination, True
                )


class TestUnifiedRepositoryAPIIntegration:
    """Integration tests for UnifiedRepositoryAPI matching real usage patterns."""

    def test_complete_workflow_github(self):
        """Test complete workflow exactly as used in api_server.py and tracked_scan.py."""
        # Setup - exactly as in api_server.py
        target = GitHubTargetConfig(organizations=['test-org'])
        filters = FiltersConfig(is_archived=False, max_repo_mb_size=1000)
        
        mock_repos = [
            BaseRepository(
                name='repo1',
                full_name='test-org/repo1',
                ssh_url='git@github.com:test-org/repo1.git',
                clone_url='https://github.com/test-org/repo1.git',
                archived=False,
                size_mb=50
            ),
            BaseRepository(
                name='repo2',
                full_name='test-org/repo2',
                ssh_url='git@github.com:test-org/repo2.git',
                clone_url='https://github.com/test-org/repo2.git',
                archived=False,
                size_mb=75
            )
        ]
        expected_urls = ['https://github.com/test-org/repo1.git', 'https://github.com/test-org/repo2.git']  # Clone URLs for get_repositories_urls()
        
        with patch('repolib.api.GITHUB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GitHubProvider') as mock_github_provider:
                mock_provider = Mock()
                mock_provider.fetch_repositories.return_value = mock_repos
                mock_github_provider.return_value = mock_provider
                
                # api_server.py pattern
                unified_api = UnifiedRepositoryAPI(
                    filters=filters, 
                    target=target,
                    cache_backend='test_cache'
                )
                
                # tracked_scan.py pattern
                mock_status_updater = Mock(spec=ProjectFetchStatusUpdater)
                
                # Line 131: fetched_projects_count = self.projects_api.fetch_repositories(project_fetch_status_updater)
                fetched_projects_count = unified_api.fetch_repositories(mock_status_updater)
                
                # Line 145: for project_url in self.projects_api.get_repositories_urls():
                project_urls = unified_api.get_repositories_urls()
                
                # Verify the complete workflow
                assert fetched_projects_count == 2
                assert project_urls == expected_urls
                assert unified_api.get_provider_type() == ProviderType.GITHUB

    def test_complete_workflow_gitlab(self):
        """Test complete workflow for GitLab provider."""
        target = GitLabTargetConfig(groups=['test-group'])
        filters = FiltersConfig(is_fork=False)
        
        mock_repos = [
            BaseRepository(
                name='project1',
                full_name='test-group/project1', 
                ssh_url='git@gitlab.com:test-group/project1.git',
                clone_url='https://gitlab.com/test-group/project1.git',
                is_fork=False
            )
        ]
        expected_urls = ['https://gitlab.com/test-group/project1.git']  # Clone URLs for get_repositories_urls()
        
        with patch('repolib.api.GITLAB_API_TOKEN', 'test_token'):
            with patch('repolib.api.GITLAB_URL', 'https://gitlab.com'):
                with patch('repolib.api.GitLabProvider') as mock_gitlab_provider:
                    mock_provider = Mock()
                    mock_provider.fetch_repositories.return_value = mock_repos
                    mock_gitlab_provider.return_value = mock_provider
                    
                    # Complete workflow test
                    unified_api = UnifiedRepositoryAPI(filters=filters, target=target)
                    mock_status_updater = Mock(spec=ProjectFetchStatusUpdater)
                    
                    fetched_count = unified_api.fetch_repositories(mock_status_updater)
                    urls = unified_api.get_repositories_urls()
                    
                    assert fetched_count == 1
                    assert urls == expected_urls
                    assert unified_api.get_provider_type() == ProviderType.GITLAB