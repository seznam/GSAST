from typing import List, Optional
from pathlib import Path
from .github_provider import GitHubProvider  
from .gitlab_provider import GitLabProvider
from .base import BaseRepository
from .status_updater import ProjectFetchStatusUpdater
from models.config_models import TargetConfig, FiltersConfig, ProviderType
from configs.repo_values import GITHUB_API_TOKEN, GITLAB_API_TOKEN, GITLAB_URL


class UnifiedRepositoryAPI:
    """Unified interface for GitHub and GitLab repositories"""
    
    def __init__(self, filters: FiltersConfig, target: TargetConfig, cache_backend=None):
        self.target = target
        self.filters = filters
        self.cache_backend = cache_backend
        self.provider = None
        self._repositories = []  # Store fetched repositories
        
        # Initialize the specific provider based on target
        if self.target.provider == ProviderType.GITHUB:
            if not GITHUB_API_TOKEN:
                raise ValueError("GitHub provider requires GITHUB_API_TOKEN environment variable")
            try:
                self.provider = GitHubProvider(GITHUB_API_TOKEN, self.cache_backend)
            except Exception as e:
                raise ValueError(f"Failed to initialize GitHub provider: {e}")
                
        elif self.target.provider == ProviderType.GITLAB:
            if not GITLAB_API_TOKEN:
                raise ValueError("GitLab provider requires GITLAB_API_TOKEN environment variable")
            try:
                self.provider = GitLabProvider(GITLAB_URL, GITLAB_API_TOKEN, self.cache_backend)
            except Exception as e:
                raise ValueError(f"Failed to initialize GitLab provider: {e}")
        else:
            raise ValueError(f"Unsupported provider: {self.target.provider}")
    
    def fetch_repositories(self, project_fetch_status_updater: ProjectFetchStatusUpdater) -> int:
        """Fetch repositories based on target configuration and filters - returns COUNT"""
        self._repositories = self.provider.fetch_repositories(self.target, self.filters, project_fetch_status_updater)
        return len(self._repositories)
    
    def get_repositories_ssh_urls(self) -> List[str]:
        """Get SSH URLs for fetched repositories - NO parameters needed"""
        return self.provider.get_repositories_ssh_urls(self._repositories)
    
    def get_repositories_urls(self) -> List[str]:
        """Get URLs for fetched repositories - NO parameters needed"""
        return [repo.clone_url for repo in self._repositories]
    
    def get_provider_type(self) -> ProviderType:
        """Get the provider type for this API instance"""
        return self.target.provider
    
    def download_repository(self, repo: BaseRepository, destination: Path, shallow: bool = True) -> bool:
        """Download a repository using the configured provider"""
        return self.provider.download_repository(repo, destination, shallow)


