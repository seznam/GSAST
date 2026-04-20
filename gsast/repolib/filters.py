import re
from datetime import datetime, timezone
from typing import Optional

from .base import BaseRepository
from models.config_models import FiltersConfig


def filter_repository(filters: Optional[FiltersConfig], repo: BaseRepository) -> bool:
    """Return True if *repo* passes all active *filters*, False otherwise.

    This is the single source of truth for repository filtering logic shared
    by both GitHubProvider and GitLabProvider.
    """
    if not filters:
        return True

    if filters.is_archived is not None and repo.archived != filters.is_archived:
        return False
    if filters.is_fork is not None and repo.is_fork != filters.is_fork:
        return False
    if filters.is_personal_project is not None and repo.is_personal_project != filters.is_personal_project:
        return False
    if filters.max_repo_mb_size is not None and repo.size_mb > filters.max_repo_mb_size:
        return False

    if filters.last_commit_max_age is not None and repo.last_activity:
        days_since_last_commit = (datetime.now(timezone.utc) - repo.last_activity).days
        if days_since_last_commit > filters.last_commit_max_age:
            return False

    if filters.ignore_path_regexes:
        for pattern in filters.ignore_path_regexes:
            if re.search(pattern, repo.full_name):
                return False

    if filters.must_path_regexes:
        if not any(re.search(pattern, repo.full_name) for pattern in filters.must_path_regexes):
            return False

    return True
