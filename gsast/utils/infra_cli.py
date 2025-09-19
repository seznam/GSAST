import argparse
import os
import sys

from redis import Redis
from rq import Queue

from configs import *
from utils.safe_logging import log


def parse_args(cli_description, is_worker=False):
    parser = argparse.ArgumentParser(description=cli_description)

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

    parser.add_argument('--api-secret-key',
                        help='API secret key, should be set in API_SECRET_KEY env variable',
                        default=API_SECRET_KEY)

    args = parser.parse_args()

    if not args.gitlab_api_token:
        log.error('Gitlab API token is not set in GITLAB_API_TOKEN env variable or --gitlab-api-token argument')
        sys.exit(1)
    if not args.github_api_token:
        log.error('GitHub API token is not set in GITHUB_API_TOKEN env variable or --github-api-token argument')
        sys.exit(1)

    if not args.redis_url:
        log.error('Redis URL is not set in REDIS_URL env variable or --redis-url argument')
        sys.exit(1)
    elif not args.redis_url.startswith('redis://') or args.redis_url.endswith('/'):
        log.error('Redis URL is not in correct format')
        sys.exit(1)

    if not is_worker and not args.api_secret_key:
        log.error('API secret key is not set in API_SECRET_KEY env variable or --api-secret-key argument')
        sys.exit(1)
    return args


def setup_redis_queues(redis_url):
    scans_redis = Redis.from_url(redis_url, db=REDIS_SCANS_DB, decode_responses=True)  # is used for API responses
    tasks_redis = Redis.from_url(redis_url, db=REDIS_TASKS_DB)
    tasks_queue = Queue('tasks', connection=tasks_redis)
    rules_redis = Redis.from_url(redis_url, db=REDIS_RULES_DB)

    return scans_redis, tasks_redis, tasks_queue, rules_redis


def setup_redis_cache(redis_url):
    projects_redis = Redis.from_url(redis_url, db=REDIS_CACHE_DB)

    return projects_redis
