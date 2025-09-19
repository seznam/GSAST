from typing import List, Optional

# project requirements to be scanned
PROJECT_IS_ARCHIVED: bool = False  # whether archived projects should be filtered out from scan
PROJECT_IS_FORK: bool = False  # whether forked projects should be filtered out from scan
PROJECT_IS_PERSONAL_PROJECT: bool = False  # whether personal projects should be filtered out from scan
PROJECT_MAX_REPO_SIZE: int = 50  # maximum repository size in MB to be included in scan
PROJECT_LAST_COMMIT_MAX_AGE: int = 0  # filter out projects with last commit time older than specified number of days, by default 0 (disabled)

PROJECT_IGNORE_PATH_REGEXES: Optional[List[str]] = None  # "path_with_namespace" regexes to be excluded from scan
PROJECT_MUST_PATH_REGEXES: Optional[List[str]] = None  # "path_with_namespace" regexes to limit scan to

# if group ids filter was specified, then all future scans will be limited to these groups until API cache expires
GITLAB_PROJECT_GROUP_IDS: Optional[List[str]] = None  # group IDs to which projects should belong
GITLAB_PROJECT_GROUP_WITH_SHARED: bool = False  # include projects shared with specified group IDs
GITLAB_PROJECT_GROUP_INCLUDE_SUBGROUPS: bool = True  # include projects in subgroups of specified group IDs

API_CACHE_EXPIRE_AFTER: int = 4  # how many weeks to use cached GitHub and GitLab API responses about existing projects

PROJECT_DOWNLOAD_TIMEOUT: int = 60 * 5  # seconds
SERVER_WAIT_FOR_WORKERS_TIMEOUT: int = 120  # seconds
SERVER_CHECK_JOBS_STATUS_INTERVAL: int = 3  # seconds
SERVER_CHECK_PROJECT_STATUS_INTERVAL: int = 1  # seconds


SERVER_JOB_TIMEOUT: str = '15m'  # minutes
SERVER_JOB_RESULT_TTL: int = 3 * 60 * 60 * 24  # seconds

REDIS_CACHE_DB: int = 0
REDIS_TASKS_DB: int = 1
REDIS_RULES_DB: int = 2
REDIS_SCANS_DB: int = 3
