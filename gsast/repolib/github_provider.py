from .base import BaseRepository
from models.config_models import TargetConfig, FiltersConfig, ProviderType
from typing import List, Optional
from pathlib import Path
import subprocess
from github import Github
from github.Auth import Token
from tqdm import tqdm
import os
import requests
import urllib3
import ssl


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
                        print(f"Could not fetch repository {repo_name}: {e}")
            
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
                        print(f"Repo info: {repo_info}")
                        
                        # Apply filters if provided  
                        if self._should_include_repo(filters, repo_info, repo):
                            repositories.append(repo_info)
                            
                    except Exception as e:
                        print(f"Error processing repository {repo.full_name}: {e}")
                        continue
            
        except Exception as e:
            print(f"Error fetching GitHub repositories: {e}")
            return []
        
        return repositories
    
    def _should_include_repo(self, filters: Optional[FiltersConfig], repo: BaseRepository, github_repo=None) -> bool:
        """Comprehensive filtering logic"""
        if not filters:
            return True
        
        # Existing filters
        if filters.is_archived is not None and repo.archived != filters.is_archived:
            return False
        if filters.is_fork is not None and repo.is_fork != filters.is_fork:
            return False
        if filters.max_repo_mb_size is not None and repo.size_mb > filters.max_repo_mb_size:
            return False
        
        # Last commit age filter
        if filters.last_commit_max_age is not None and repo.last_activity:
            from datetime import datetime, timezone
            days_since_last_commit = (datetime.now(timezone.utc) - repo.last_activity).days
            if days_since_last_commit > filters.last_commit_max_age:
                return False
        
        # Path regex filters - ignore patterns (exclude repos matching these patterns)
        if filters.ignore_path_regexes:
            import re
            for pattern in filters.ignore_path_regexes:
                if re.search(pattern, repo.full_name):
                    return False
        
        # Path regex filters - must patterns (only include repos matching at least one pattern)
        if filters.must_path_regexes:
            import re
            matches_required_pattern = False
            for pattern in filters.must_path_regexes:
                if re.search(pattern, repo.full_name):
                    matches_required_pattern = True
                    break
            if not matches_required_pattern:
                return False
        
        # Personal project filter - for GitHub, check if owner is a user (not organization)
        if filters.is_personal_project is not None and github_repo:
            try:
                # GitHub repos have owner.type that tells us if it's 'User' or 'Organization'
                is_personal = False
                if hasattr(github_repo, 'owner') and github_repo.owner:
                    owner_type = getattr(github_repo.owner, 'type', None)
                    is_personal = (owner_type == 'User')
                
                if is_personal != filters.is_personal_project:
                    return False
            except Exception as e:
                # If we can't determine the project type, log and continue
                print(f"Warning: Could not determine if repository {repo.full_name} is personal: {e}")
        
        return True
    
    def get_repositories_ssh_urls(self, repositories: List[BaseRepository]) -> List[str]:
        """Get SSH URLs for all repositories"""
        return [repo.ssh_url for repo in repositories if repo.ssh_url]
    
    def _convert_github_repo(self, repo) -> BaseRepository:
        """Convert GitHub repository to BaseRepository"""
        
        return BaseRepository(
            name=repo.name,
            full_name=repo.full_name,
            description=repo.description or '',
            clone_url=repo.clone_url,
            ssh_url=repo.ssh_url,
            web_url=repo.html_url,
            size_mb=repo.size / 1024 if repo.size else 0,  # Convert KB to MB
            stars=repo.stargazers_count,
            forks=repo.forks_count,
            language=repo.language or '',
            archived=repo.archived,
            is_fork=repo.fork,
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
                print(f"Successfully downloaded {repo.full_name}")
                return True
            else:
                print(f"Failed to download {repo.full_name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"Error downloading {repo.full_name}: {e}")
            return False