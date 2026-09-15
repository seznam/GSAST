import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional

import gitlab

from .base import BaseRepository
from .filters import filter_repository
from gsast_core.models.config_models import TargetConfig, FiltersConfig, ProviderType
from gsast_core.utils.safe_logging import log


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

    @staticmethod
    def _base_list_kwargs(filters: Optional[FiltersConfig]) -> dict:
        """Common python-gitlab list() kwargs: stream pages, never materialize all=True."""
        kwargs = {'iterator': True, 'per_page': 100}
        if filters is not None and filters.is_archived is not None:
            kwargs['archived'] = filters.is_archived
        return kwargs

    def _list_projects(self, manager, filters: Optional[FiltersConfig], extra_kwargs: Optional[dict] = None):
        """List projects as a generator.

        Prefer GitLab keyset pagination so large instances (>10k projects, where
        X-Total is omitted) do not load every REST object into memory.
        """
        kwargs = {**self._base_list_kwargs(filters), **(extra_kwargs or {})}
        try:
            return manager.list(pagination='keyset', order_by='id', **kwargs)
        except TypeError:
            return manager.list(**kwargs)
        except Exception as e:
            log.warning(f'GitLab keyset listing failed ({e}); falling back to offset pagination')
            return manager.list(**kwargs)

    def _iter_project_sources(self, target: TargetConfig, filters: Optional[FiltersConfig]) -> Iterator:
        """Yield GitLab project objects without accumulating them in a list."""
        yielded = False

        if target.groups:
            for group_name in target.groups:
                try:
                    group = self.client.groups.get(group_name)
                    for project in self._list_projects(
                        group.projects, filters, {'include_subgroups': True}
                    ):
                        yielded = True
                        yield project
                except Exception as e:
                    log.warning(f'Could not fetch group {group_name}: {e}')

        if target.repositories:
            for repo_name in target.repositories:
                try:
                    yielded = True
                    yield self.client.projects.get(repo_name)
                except Exception as e:
                    log.warning(f'Could not fetch repository {repo_name}: {e}')

        if not yielded and not target.groups and not target.repositories:
            yield from self._list_projects(
                self.client.projects, filters, {'with_shared': True}
            )

    @staticmethod
    def _needs_repository_size(filters: Optional[FiltersConfig]) -> bool:
        return filters is not None and filters.max_repo_mb_size is not None

    def _hydrate_project_if_needed(self, project, filters: Optional[FiltersConfig]):
        """GET /projects/:id only when the size filter needs statistics the list payload lacks."""
        if not self._needs_repository_size(filters):
            return project
        statistics = getattr(project, 'statistics', None)
        if statistics:
            return project
        return self.client.projects.get(project.id, statistics=True)

    def fetch_repositories(self, target: TargetConfig, filters: Optional[FiltersConfig], project_fetch_status_updater) -> List[BaseRepository]:
        """Fetch GitLab repositories based on target configuration"""

        if target.provider != ProviderType.GITLAB:
            raise ValueError("GitLab provider can only handle GitLab targets")

        repositories: List[BaseRepository] = []
        processed = 0

        try:
            for project in self._iter_project_sources(target, filters):
                processed += 1
                try:
                    if project_fetch_status_updater and processed % 50 == 1:
                        project_fetch_status_updater.update_callback(
                            f'Fetching projects ({processed} processed, {len(repositories)} matched)'
                        )

                    full_project = self._hydrate_project_if_needed(project, filters)
                    repo_info = self._convert_gitlab_project(full_project)
                    log.debug(f'Repo info: {repo_info}')

                    if self._should_include_repo(filters, repo_info, full_project):
                        repositories.append(repo_info)

                    if processed % 500 == 0:
                        log.info(
                            f'GitLab fetch progress: {processed} processed, {len(repositories)} matched'
                        )
                except Exception as e:
                    name = getattr(project, 'path_with_namespace', getattr(project, 'id', '?'))
                    log.warning(f'Error processing project {name}: {e}')
                    continue
        except Exception as e:
            log.error(f'Error fetching GitLab repositories: {e}')
            raise

        if project_fetch_status_updater:
            project_fetch_status_updater.update_callback(
                f'Fetching projects ({processed} processed, {len(repositories)} matched)'
            )
        log.info(f'GitLab fetch finished: {processed} processed, {len(repositories)} matched')
        return repositories

    def _should_include_repo(self, filters: Optional[FiltersConfig], repo: BaseRepository, project=None) -> bool:
        return filter_repository(filters, repo)

    def get_repositories_ssh_urls(self, repositories: List[BaseRepository]) -> List[str]:
        """Get SSH URLs for all repositories"""
        return [repo.ssh_url for repo in repositories if repo.ssh_url]

    @staticmethod
    def _namespace_info(namespace) -> tuple:
        """Return (owner_path, is_personal_project) from a dict or REST object."""
        if not namespace:
            return '', False
        if isinstance(namespace, dict):
            return namespace.get('path', '') or '', namespace.get('kind') == 'user'
        return getattr(namespace, 'path', '') or '', getattr(namespace, 'kind', None) == 'user'

    @staticmethod
    def _parse_gitlab_datetime(value, project, field_label: str):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except Exception as e:
            name = getattr(project, 'path_with_namespace', getattr(project, 'id', '?'))
            log.error(f'Error parsing {field_label} of project {name}: {e}')
            return None

    @staticmethod
    def _repository_size_mb(project) -> float:
        try:
            statistics = getattr(project, 'statistics', None)
            if not statistics:
                return 0
            if isinstance(statistics, dict):
                repo_size = statistics.get('repository_size', 0) or 0
            else:
                repo_size = getattr(statistics, 'repository_size', 0) or 0
            return repo_size / (1024 * 1024)
        except Exception as e:
            name = getattr(project, 'path_with_namespace', getattr(project, 'id', '?'))
            log.error(f'Error calculating size of project {name}: {e}')
            return 0

    def _convert_gitlab_project(self, project) -> BaseRepository:
        """Convert GitLab project to BaseRepository"""
        owner, is_personal_project = self._namespace_info(getattr(project, 'namespace', None))

        return BaseRepository(
            name=getattr(project, 'name', ''),
            full_name=getattr(project, 'path_with_namespace', ''),
            description=getattr(project, 'description', None) or '',
            clone_url=getattr(project, 'http_url_to_repo', ''),
            ssh_url=getattr(project, 'ssh_url_to_repo', ''),
            web_url=getattr(project, 'web_url', ''),
            size_mb=self._repository_size_mb(project),
            stars=getattr(project, 'star_count', 0) or 0,
            forks=getattr(project, 'forks_count', 0) or 0,
            language='',
            archived=bool(getattr(project, 'archived', False)),
            is_fork=getattr(project, 'forked_from_project', None) is not None,
            is_personal_project=is_personal_project,
            last_activity=self._parse_gitlab_datetime(
                getattr(project, 'last_activity_at', None), project, 'last activity'
            ),
            created_at=self._parse_gitlab_datetime(
                getattr(project, 'created_at', None), project, 'created date'
            ),
            owner=owner,
            private=getattr(project, 'visibility', None) == 'private',
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
                log.info(f"Successfully downloaded {repo.full_name}")
                return True
            else:
                log.error(f"Failed to download {repo.full_name}: {result.stderr}")
                return False

        except Exception as e:
            log.error(f"Error downloading {repo.full_name}: {e}")
            return False
