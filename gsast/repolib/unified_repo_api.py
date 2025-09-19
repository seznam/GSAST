from configs.repo_values import RepositoryConfig, RepositoryFilters
from .api import UnifiedRepositoryAPI
from models.config_models import ProviderType
from pathlib import Path

def main():
    """Example usage of the Unified Repository API"""
    
    # Initialize API with environment variables
    config = RepositoryConfig()
    api = UnifiedRepositoryAPI(config)
    
    # Create custom filters
    filters = RepositoryFilters(
        exclude_archived=True,
        exclude_forks=True,
        max_repo_size_mb=100,  # Max 100MB
        last_commit_max_age_days=365,  # Active within last year
        ignore_path_regexes=[r'.*-archive$', r'.*deprecated.*'],
        must_path_regexes=[r'.*python.*']  # Must contain 'python'
    )
    
    # Fetch repositories from GitHub organization
    try:
        github_repos = api.fetch_repositories(
            ProviderType.GITHUB,
            organization='seznam',
            filters=filters
        )
        print(f"Found {len(github_repos)} GitHub repositories")
    except Exception as e:
        print(f"GitHub fetch failed: {e}")
        github_repos = []
    
    # Fetch repositories from GitLab group
    # try:
    #     gitlab_repos = api.fetch_repositories(
    #         ProviderType.GITLAB,
    #         group='your-group',
    #         filters=filters
    #     )
    #     print(f"Found {len(gitlab_repos)} GitLab repositories")
    # except Exception as e:
    #     print(f"GitLab fetch failed: {e}")
    #     gitlab_repos = []
    
    # Combine all repositories
    all_repos = github_repos
    
    # Print repository information
    for repo in all_repos[:5]:  # Show first 5
        print(f"Repository: {repo.full_name}")
        print(f"  Description: {repo.description}")
        print(f"  Language: {repo.language}")
        print(f"  Stars: {repo.stars}")
        print(f"  Size: {repo.size_mb:.1f} MB")
        print(f"  Last activity: {repo.last_activity}")
        print()
    
    # Download repositories
    if all_repos:
        download_path = Path('./downloaded_repos')
        results = api.download_repositories(all_repos[:3], download_path, shallow=True)
        
        print(f"Download results:")
        print(f"  Successful: {len(results['success'])}")
        print(f"  Failed: {len(results['failed'])}")


if __name__ == '__main__':
    main()