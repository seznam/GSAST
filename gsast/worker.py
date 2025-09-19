import os
import sys
import shutil
from pathlib import Path

from rq import Worker

from utils import infra_cli
import sastlib.ruleset_downloader as ruleset_downloader
import sastlib.semgrep_api as semgrep_api
import sastlib.trufflehog_api as trufflehog_api
import sastlib.dependency_confusion_api as dependency_confusion_api
import sastlib.results_storage as results_storage
import repolib.downloader.gitlab_downloader as gitlab_downloader
import repolib.downloader.github_downloader as github_downloader
from utils.safe_logging import log


def exit_with_cleanup(project_sources_dir=None):
    if project_sources_dir and os.path.exists(project_sources_dir):
        shutil.rmtree(project_sources_dir)
    sys.exit(1)


def process_task(scan_id, project_ssh_url, rule_keys, scanners, project_url=None):
    scans_redis, tasks_redis, tasks_queue, rules_redis, unified_project_downloader, sast_ruleset_downloader, args = main_cli()
    
    # Determine project path using the unified downloader
    project_path_with_namespace = unified_project_downloader.get_project_path(project_ssh_url)
    
    # Determine if we need secrets scanning for git clone strategy
    scan_secrets = 'trufflehog' in scanners
    
    log.info(f'Processing task for project: {project_path_with_namespace} with scan_id: {scan_id} with scanners: {scanners}')

    rules_dir = sast_ruleset_downloader.get_rules(rule_keys)
    if not rules_dir and 'semgrep' in scanners:
        log.error(f'Failed to download rules for scan_id: {scan_id}')
        exit_with_cleanup()

    use_partial_git_clone = not scan_secrets
    download_result = unified_project_downloader.download_project(project_ssh_url, scan_id, use_partial_git_clone)
    if not download_result:
        log.error(f'Failed to download project sources for scan_id: {scan_id}')
        exit_with_cleanup()
    
    project_sources_dir, project_parent_dir = download_result

    try:
        has_upload_errors = False

        # Run semgrep scan if configured
        if 'semgrep' in scanners:
            sarif_results = semgrep_api.run_scan(project_sources_dir, project_parent_dir, rules_dir)
            if sarif_results:
                log.info(f'Semgrep results: {sarif_results}')
                # Store results in Redis
                store_ok = results_storage.store_scan_results(
                    scans_redis, scan_id, project_url, 'semgrep', sarif_results
                )
                if not store_ok:
                    log.error(f'Failed to store Semgrep results in Redis for scan_id: {scan_id}')
                    has_upload_errors = True
            else:
                log.debug(f'No sarif results for scan_id: {scan_id}')
        else:
            log.info(f'Skipping semgrep scan (not in configured scanners): {scanners}')

        # Run trufflehog scan if configured
        if 'trufflehog' in scanners:
            secrets_results = trufflehog_api.run_scan(project_sources_dir, project_parent_dir)
            if secrets_results:
                log.info(f'Trufflehog results: {secrets_results}')
                # Store results in Redis
                store_ok = results_storage.store_scan_results(
                    scans_redis, scan_id, project_url, 'trufflehog', secrets_results
                )
                if not store_ok:
                    log.error(f'Failed to store Trufflehog results in Redis for scan_id: {scan_id}')
                    has_upload_errors = True
            else:
                log.debug(f'No secrets results for scan_id: {scan_id}')
        else:
            log.info(f'Skipping trufflehog scan (not in configured scanners): {scanners}')
        
        # Run dependency confusion scan if configured
        if 'dependency-confusion' in scanners:
            dependency_confusion_results = dependency_confusion_api.run_scan(Path(project_sources_dir), Path(project_parent_dir))
            if dependency_confusion_results:
                log.info(f'Dependency confusion results: {dependency_confusion_results}')
                # Store results in Redis
                store_ok = results_storage.store_scan_results(
                    scans_redis, scan_id, project_url, 'dependency-confusion', dependency_confusion_results
                )
                if not store_ok:
                    log.error(f'Failed to store Dependency Confusion results in Redis for scan_id: {scan_id}')
                    has_upload_errors = True
            else:
                log.debug(f'No dependency confusion results for scan_id: {scan_id}')
        else:
            log.info(f'Skipping dependency confusion scan (not in configured scanners): {scanners}')
        
        if has_upload_errors:
            log.error(f'Failed to store results for scan_id: {scan_id}')
            exit_with_cleanup(project_sources_dir)

        log.info(f'Finished processing task for project: {project_path_with_namespace} with scan_id: {scan_id}')

    except Exception as e:
        log.error(f'Failed to run scan for scan_id: {scan_id}', exc_info=e)
        exit_with_cleanup(project_sources_dir)


def determine_provider_from_url(project_url: str) -> str:
    """Determine if the project URL is from GitHub or GitLab"""
    # Handle both SSH and HTTPS URLs
    if 'github.com' in project_url:
        return 'github'
    elif 'gitlab' in project_url:
        return 'gitlab'
    else:
        # Default to GitLab for unknown URLs
        log.warning(f"Unknown repository provider for URL: {project_url}, defaulting to GitLab")
        return 'gitlab'


class UnifiedProjectDownloader:
    """Unified downloader that routes to appropriate provider-specific downloader"""
    
    def __init__(self, gitlab_url, gitlab_api_token, github_api_token):
        self.gitlab_downloader = gitlab_downloader.GitLabProjectDownloader(gitlab_url, gitlab_api_token)
        self.github_downloader = github_downloader.GitHubProjectDownloader(github_api_token)
    
    def get_project_path(self, project_url: str):
        """Get project path using the appropriate downloader"""
        provider = determine_provider_from_url(project_url)
        if provider == 'github':
            return self.github_downloader.get_project_path(project_url)
        else:
            return self.gitlab_downloader.get_project_path(project_url)
    
    def download_project(self, project_url: str, project_parent_dir_name: str, use_shallow_clone: bool = True):
        """Download project using the appropriate downloader"""
        provider = determine_provider_from_url(project_url)
        log.info(f"Using {provider} downloader for URL: {project_url}")
        
        if provider == 'github':
            return self.github_downloader.download_project(project_url, project_parent_dir_name, use_shallow_clone)
        else:
            return self.gitlab_downloader.download_project(project_url, project_parent_dir_name, use_shallow_clone)


def main_cli():
    args = infra_cli.parse_args('Process tasks from Redis',
                                is_worker=True)
    scans_redis, tasks_redis, tasks_queue, rules_redis = infra_cli.setup_redis_queues(args.redis_url)
    unified_project_downloader = UnifiedProjectDownloader(args.gitlab_url, args.gitlab_api_token, args.github_api_token)
    sast_ruleset_downloader = ruleset_downloader.RulesetDownloader(rules_redis)

    return scans_redis, tasks_redis, tasks_queue, rules_redis, unified_project_downloader, sast_ruleset_downloader, args


def wait_for_tasks():
    scans_redis, tasks_redis, tasks_queue, rules_redis, unified_project_downloader, sast_ruleset_downloader, args = main_cli()
    tasks_queue_worker = Worker([tasks_queue], connection=tasks_redis)
    tasks_queue_worker.work()


def main():
    wait_for_tasks()


if __name__ == '__main__':
    main()
