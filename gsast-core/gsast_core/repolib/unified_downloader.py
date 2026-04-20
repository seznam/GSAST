from typing import Optional, Tuple
from pathlib import Path, PurePath

from gsast_core.utils.safe_logging import log
from gsast_core.repolib.downloader.gitlab_downloader import GitLabProjectDownloader
from gsast_core.repolib.downloader.github_downloader import GitHubProjectDownloader


def determine_provider_from_url(project_url: str) -> str:
    """Determine if the project URL is from GitHub or GitLab."""
    if 'github.com' in project_url:
        return 'github'
    elif 'gitlab' in project_url:
        return 'gitlab'
    else:
        log.warning(f"Unknown repository provider for URL: {project_url}, defaulting to GitLab")
        return 'gitlab'


class UnifiedProjectDownloader:
    """Unified downloader that routes to the appropriate provider-specific downloader."""

    def __init__(self, gitlab_url: str, gitlab_api_token: str, github_api_token: Optional[str] = None):
        self.gitlab_downloader = GitLabProjectDownloader(gitlab_url, gitlab_api_token)
        self.github_downloader = GitHubProjectDownloader(github_api_token)

    def get_project_path(self, project_url: str) -> PurePath:
        """Get project path using the appropriate downloader."""
        provider = determine_provider_from_url(project_url)
        if provider == 'github':
            return self.github_downloader.get_project_path(project_url)
        return self.gitlab_downloader.get_project_path(project_url)

    def download_project(self, project_url: str, project_parent_dir_name: str, use_shallow_clone: bool = True) -> Optional[Tuple[Path, Path]]:
        """Download project using the appropriate downloader."""
        provider = determine_provider_from_url(project_url)
        log.info(f"Using {provider} downloader for URL: {project_url}")
        if provider == 'github':
            return self.github_downloader.download_project(project_url, project_parent_dir_name, use_shallow_clone)
        return self.gitlab_downloader.download_project(project_url, project_parent_dir_name, use_shallow_clone)
