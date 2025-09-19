import gitlab
from .base import BaseRepository
from models.config_models import TargetConfig, FiltersConfig, ProviderType
from typing import List, Optional
from pathlib import Path
import subprocess
from datetime import datetime
from tqdm import tqdm
from utils.safe_logging import log
import os


class GitLabProvider:
    """GitLab repository provider"""
    
    def __init__(self, gitlab_url: str, GITLAB_API_TOKEN: str, cache_backend=None):
        self.gitlab_url = gitlab_url
        self.GITLAB_API_TOKEN = GITLAB_API_TOKEN
        self.cache_backend = cache_backend
        
        # Initialize GitLab client
        # Honor a custom CA bundle if provided (path or boolean)
        ca_bundle_path = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
        ssl_verify: object
        if ca_bundle_path and isinstance(ca_bundle_path, str) and ca_bundle_path.strip():
            ssl_verify = ca_bundle_path.strip()
        else:
            ssl_verify = True

        self.client = gitlab.Gitlab(
            gitlab_url,
            private_token=GITLAB_API_TOKEN,
            ssl_verify=ssl_verify,
        )
        self.client.auth()
        
        # Test authentication
        try:
            self.client.user
        except Exception as e:
            raise ValueError(f"GitLab authentication failed: {e}")
    
    def fetch_repositories(self, target: TargetConfig, filters: Optional[FiltersConfig], project_fetch_status_updater) -> List[BaseRepository]:
        """Fetch GitLab repositories based on target configuration"""
        
        if target.provider != ProviderType.GITLAB:
            raise ValueError("GitLab provider can only handle GitLab targets")
            
        repositories = []
        projects_sources = []
        
        try:
            # Handle groups
            if target.groups:
                for group_name in target.groups:
                    try:
                        group = self.client.groups.get(group_name, include_subgroups=True)
                        projects_sources.extend(group.projects.list(all=True))
                    except Exception as e:
                        print(f"Could not fetch group {group_name}: {e}")
            
            # Handle specific repositories
            if target.repositories:
                for repo_name in target.repositories:
                    try:
                        project = self.client.projects.get(repo_name)
                        projects_sources.append(project)
                    except Exception as e:
                        print(f"Could not fetch repository {repo_name}: {e}")
            
            # If no specific targets, get all accessible projects in the GitLab instance
            if not projects_sources:
                projects_sources = self.client.projects.list(iterator=True, all=True, include_subgroups=True, with_shared=True)
            
            # Process all projects
            total_projects = len(projects_sources)
            for i, project in enumerate(tqdm(projects_sources, 
                              desc="Loading projects from GitLab (this may take a while)",
                              unit=' projects', 
                              file=project_fetch_status_updater.status_file, 
                              position=0,
                              disable=project_fetch_status_updater is None), 1):
                try:
                    # Update status with progress info
                    if project_fetch_status_updater:
                        progress_message = f"Fetching projects {i}/{total_projects}"
                        project_fetch_status_updater.update_callback(progress_message)
                    
                    # Get full project details if needed
                    if not hasattr(project, 'statistics'):
                        full_project = self.client.projects.get(project.id, statistics=True)
                    else:
                        full_project = project
                    
                    # Convert GitLab project to BaseRepository
                    repo_info = self._convert_gitlab_project(full_project)
                    log.info(f"Repo info: {repo_info}")
                    
                    # Apply filters if provided
                    if self._should_include_repo(filters, repo_info, full_project):
                        repositories.append(repo_info)
                        
                except Exception as e:
                    print(f"Error processing project {project.path_with_namespace}: {e}")
                    continue
            
        except Exception as e:
            print(f"Error fetching GitLab repositories: {e}")
            return []
        
        return repositories
    
    def _should_include_repo(self, filters: Optional[FiltersConfig], repo: BaseRepository, project=None) -> bool:
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
        
        # Personal project filter - for GitLab, check namespace kind
        if filters.is_personal_project is not None and project:
            try:
                # GitLab projects have namespace information that tells us if it's personal or group
                is_personal = False
                if hasattr(project, 'namespace') and project.namespace:
                    # In GitLab, personal projects have namespace.kind == 'user'
                    # Group projects have namespace.kind == 'group'
                    namespace_kind = getattr(project.namespace, 'kind', None)
                    is_personal = (namespace_kind == 'user')
                
                if is_personal != filters.is_personal_project:
                    return False
            except Exception as e:
                # If we can't determine the project type, log and continue
                print(f"Warning: Could not determine if project {repo.full_name} is personal: {e}")
        
        return True
    
    def get_repositories_ssh_urls(self, repositories: List[BaseRepository]) -> List[str]:
        """Get SSH URLs for all repositories"""
        return [repo.ssh_url for repo in repositories if repo.ssh_url]
    
    def _convert_gitlab_project(self, project) -> BaseRepository:
        """Convert GitLab project to BaseRepository"""
        
        # Calculate size in MB
        size_mb = 0
        try:
            if hasattr(project, 'statistics') and project.statistics:
                size_mb = project.statistics.get('repository_size', 0) / (1024 * 1024)
        except Exception as e:
            log.error(f"Error calculating size of project {project.path_with_namespace}: {e}")
        
        # Parse last activity date
        last_activity = None
        try:
            if project.last_activity_at:
                last_activity = datetime.fromisoformat(project.last_activity_at.replace('Z', '+00:00'))
        except Exception as e:
            log.error(f"Error parsing last activity of project {project.path_with_namespace}: {e}")
        
        # Parse created date
        created_at = None
        try:
            if project.created_at:
                created_at = datetime.fromisoformat(project.created_at.replace('Z', '+00:00'))
        except Exception as e:
            log.error(f"Error parsing created date of project {project.path_with_namespace}: {e}")
        
        return BaseRepository(
            name=project.name,
            full_name=project.path_with_namespace,
            description=project.description or '',
            clone_url=project.http_url_to_repo,
            ssh_url=project.ssh_url_to_repo,
            web_url=project.web_url,
            size_mb=size_mb,
            stars=project.star_count if hasattr(project, 'star_count') else 0,
            forks=project.forks_count if hasattr(project, 'forks_count') else 0,
            language=project.default_branch if hasattr(project, 'default_branch') else '',
            archived=project.archived,
            is_fork=hasattr(project, 'forked_from_project'),
            last_activity=last_activity,
            created_at=created_at,
            owner=project.namespace.get('path', ''),
            private=project.visibility == 'private'
        )
    
    def download_repository(self, repo: BaseRepository, destination: Path, shallow: bool = True) -> bool:
        """Download GitLab repository using git clone"""
        
        try:
            # Create destination directory
            destination.mkdir(parents=True, exist_ok=True)
            
            # Prepare git clone command
            cmd = ['git', 'clone']
            if shallow:
                cmd.extend(['--depth=1', '--single-branch'])
            
            # Use authenticated URL
            clone_url = repo.clone_url
            if self.GITLAB_API_TOKEN:
                # Replace https:// with https://oauth2:token@
                clone_url = clone_url.replace('https://', f'https://oauth2:{self.GITLAB_API_TOKEN}@')
            
            cmd.extend([clone_url, str(destination / repo.name)])
            
            # Execute git clone
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                print(f"Successfully downloaded {repo.full_name}")
                return True
            else:
                print(f"Failed to download {repo.full_name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"Error downloading {repo.full_name}: {e}")
            return False