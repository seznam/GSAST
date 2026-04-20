import re
import os
import subprocess
import urllib3
import requests
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from github import Github
from github.Auth import Token
from tqdm import tqdm

from .base import BaseRepository
from .filters import filter_repository
from gsast_core.models.config_models import TargetConfig, FiltersConfig, ProviderType
from gsast_core.utils.safe_logging import log


class GitHubProvider:
    """GitHub repository provider"""

    def __init__(self, GITHUB_API_TOKEN: str, cache_backend=None):
        self.GITHUB_API_TOKEN = GITHUB_API_TOKEN
        self.cache_backend = cache_backend

        # Determine SSL verification strategy
        self.ssl_verify = self._determine_ssl_verification()

        # Only disable SSL warnings if verification is disabled
        if not self.ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            # Initialize GitHub client with appropriate SSL verification
            self.client = Github(auth=Token(GITHUB_API_TOKEN), verify=self.ssl_verify)

            # Test authentication
            self.client.get_user()
        except Exception as e:
            raise ValueError(f"GitHub authentication failed: {e}")

    def _determine_ssl_verification(self):
        """Determine appropriate SSL verification strategy for GitHub API calls.

        Returns:
            bool or str: True for standard verification, False to disable, or path to CA bundle
        """
        # Check for explicit environment variable to disable SSL verification
        if os.environ.get('GITHUB_DISABLE_SSL_VERIFY', '').lower() in ('true', '1', 'yes'):
            return False

        # Honor custom CA bundle if provided (for corporate networks)
        ca_bundle_path = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
        if ca_bundle_path and isinstance(ca_bundle_path, str) and ca_bundle_path.strip():
            return ca_bundle_path.strip()

        # Default: Enable SSL verification for github.com (it has valid certificates)
        return True

    def fetch_repositories(self, target: TargetConfig, filters: Optional[FiltersConfig], project_fetch_status_updater) -> List[BaseRepository]:
        """Fetch GitHub repositories based on target configuration"""

        if target.provider != ProviderType.GITHUB:
            raise ValueError("GitHub provider can only handle GitHub targets")

        repositories = []
        repos_sources = []

        try:
            # Handle organizations
            if target.organizations:
                for org_name in target.organizations:
                    org = self.client.get_organization(org_name)
                    repos_sources.append(org.get_repos())

            if target.repositories:
                for repo_name in target.repositories:
                    try:
                        repo = self.client.get_repo(repo_name)
                        repos_sources.append([repo])  # Wrap single repo in list
                    except Exception as e:
                        log.warning(f"Could not fetch repository {repo_name}: {e}")

            if not repos_sources:
                raise ValueError("No repositories specified in the target configuration")

            # Process all repository sources
            for repos in repos_sources:
                # Convert to list to get total count
                repos_list = list(repos)
                total_repos = len(repos_list)

                for i, repo in enumerate(tqdm(repos_list,
                              desc="Loading projects from GitHub (this may take a while)",
                              unit=' projects',
                              file=project_fetch_status_updater.status_file,
                              position=0)):
                    try:
                        # Update status with progress info
                        if project_fetch_status_updater:
                            progress_message = f"Fetching projects {i}/{total_repos}"
                            project_fetch_status_updater.update_callback(progress_message)

                        # Convert GitHub repo to BaseRepository
                        repo_info = self._convert_github_repo(repo)
                        log.debug(f"Repo info: {repo_info}")

                        # Apply filters if provided
                        if self._should_include_repo(filters, repo_info, repo):
                            repositories.append(repo_info)

                    except Exception as e:
                        log.error(f"Error processing repository {repo.full_name}: {e}")
                        continue

        except Exception as e:
            log.error(f"Error fetching GitHub repositories: {e}")
            return []

        return repositories

    def _should_include_repo(self, filters: Optional[FiltersConfig], repo: BaseRepository, github_repo=None) -> bool:
        return filter_repository(filters, repo)

    def get_repositories_ssh_urls(self, repositories: List[BaseRepository]) -> List[str]:
        """Get SSH URLs for all repositories"""
        return [repo.ssh_url for repo in repositories if repo.ssh_url]

    def _convert_github_repo(self, repo) -> BaseRepository:
        """Convert GitHub repository to BaseRepository"""

        owner_type = getattr(repo.owner, 'type', None) if hasattr(repo, 'owner') and repo.owner else None
        is_personal_project = owner_type == 'User'

        return BaseRepository(
            name=repo.name,
            full_name=repo.full_name,
            description=repo.description or '',
            clone_url=repo.clone_url,
            ssh_url=repo.ssh_url,
            web_url=repo.html_url,
            size_mb=repo.size / 1024 if repo.size else 0,
            stars=repo.stargazers_count,
            forks=repo.forks_count,
            language=repo.language or '',
            archived=repo.archived,
            is_fork=repo.fork,
            is_personal_project=is_personal_project,
            last_activity=repo.pushed_at,
            created_at=repo.created_at,
            owner=repo.owner.login,
            private=repo.private
        )

    def download_repository(self, repo: BaseRepository, destination: Path, shallow: bool = True) -> bool:
        """Download GitHub repository using git clone"""

        try:
            # Create destination directory
            destination.mkdir(parents=True, exist_ok=True)

            # Prepare git clone command
            cmd = ['git', 'clone']
            if shallow:
                cmd.extend(['--depth=1', '--single-branch'])

            # Use authenticated URL if token is available
            clone_url = repo.clone_url
            if self.GITHUB_API_TOKEN and clone_url.startswith('https://github.com/'):
                clone_url = clone_url.replace('https://github.com/',
                                            f'https://{self.GITHUB_API_TOKEN}@github.com/')

            cmd.extend([clone_url, str(destination / repo.name)])

            # Set up environment for git operations
            env = os.environ.copy()

            # Only disable SSL verification for git if API verification is also disabled
            if not self.ssl_verify:
                env['GIT_SSL_NO_VERIFY'] = '1'
                # Remove SSL_CERT_FILE from git environment to prevent SSL issues
                if 'SSL_CERT_FILE' in env:
                    del env['SSL_CERT_FILE']

            # Execute git clone
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

            if result.returncode == 0:
                log.info(f"Successfully downloaded {repo.full_name}")
                return True
            else:
                log.error(f"Failed to download {repo.full_name}: {result.stderr}")
                return False

        except Exception as e:
            log.error(f"Error downloading {repo.full_name}: {e}")
            return False
