import os

GITHUB_URL = os.getenv('GITHUB_URL', 'https://api.github.com')
GITLAB_URL = os.getenv('GITLAB_URL', 'https://gitlab.com')
GITHUB_API_TOKEN = os.getenv('GITHUB_API_TOKEN')
GITLAB_API_TOKEN = os.getenv('GITLAB_API_TOKEN')
RATE_LIMIT = int(os.getenv('RATE_LIMIT', 5000))
REDIS_URL = os.getenv('REDIS_URL')
