import argparse
import sys

from redis import Redis
from rq import Queue, Worker

import gsast_core.sastlib.ruleset_downloader as ruleset_downloader
from gsast_core.configs import (
    GITHUB_API_TOKEN,
    GITHUB_URL,
    GITLAB_API_TOKEN,
    GITLAB_URL,
    REDIS_RULES_DB,
    REDIS_SCANS_DB,
    REDIS_TASKS_DB,
    REDIS_URL,
)
from gsast_core.repolib import UnifiedProjectDownloader
from gsast_core.utils.safe_logging import log
from gsast_worker.tasks import init_ctx


def _parse_args():
    parser = argparse.ArgumentParser(description='Process tasks from Redis')

    parser.add_argument('--gitlab-url',
                        help='Gitlab URL, should be set in GITLAB_URL env variable. Default: https://gitlab.com',
                        default=GITLAB_URL)
    parser.add_argument('--gitlab-api-token',
                        help='Gitlab API token, should be set in GITLAB_API_TOKEN env variable',
                        default=GITLAB_API_TOKEN)
    parser.add_argument('--github-api-token',
                        help='GitHub API token, should be set in GITHUB_API_TOKEN env variable',
                        default=GITHUB_API_TOKEN)
    parser.add_argument('--github-url',
                        help='GitHub URL, should be set in GITHUB_URL env variable. Default: https://github.com',
                        default=GITHUB_URL)
    parser.add_argument('--redis-url',
                        help='Redis URL, should be set in REDIS_URL env variable. Example: redis://:password@host:port',
                        default=REDIS_URL)

    args = parser.parse_args()

    if not args.gitlab_api_token and not args.github_api_token:
        log.error('At least one provider token must be set: GITLAB_API_TOKEN or GITHUB_API_TOKEN')
        sys.exit(1)
    if not args.gitlab_api_token:
        log.warning('GITLAB_API_TOKEN is not set — GitLab scanning will be unavailable')
    if not args.github_api_token:
        log.warning('GITHUB_API_TOKEN is not set — GitHub scanning will be unavailable')

    if not args.redis_url:
        log.error('Redis URL is not set in REDIS_URL env variable or --redis-url argument')
        sys.exit(1)
    elif not args.redis_url.startswith('redis://') or args.redis_url.endswith('/'):
        log.error('Redis URL is not in correct format')
        sys.exit(1)

    return args


def wait_for_tasks():
    args = _parse_args()

    scans_redis = Redis.from_url(args.redis_url, db=REDIS_SCANS_DB, decode_responses=True)
    tasks_redis = Redis.from_url(args.redis_url, db=REDIS_TASKS_DB)
    tasks_queue = Queue('tasks', connection=tasks_redis)
    rules_redis = Redis.from_url(args.redis_url, db=REDIS_RULES_DB)

    unified_project_downloader = UnifiedProjectDownloader(
        args.gitlab_url, args.gitlab_api_token, args.github_api_token
    )
    sast_ruleset_downloader = ruleset_downloader.RulesetDownloader(rules_redis)

    init_ctx(scans_redis, rules_redis, unified_project_downloader, sast_ruleset_downloader)

    tasks_queue_worker = Worker([tasks_queue], connection=tasks_redis)
    tasks_queue_worker.work()


def main():
    wait_for_tasks()


if __name__ == '__main__':
    main()
