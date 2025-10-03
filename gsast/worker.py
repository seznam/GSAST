import os
import sys
import shutil
from pathlib import Path

from rq import Worker

from utils import infra_cli
import sastlib.ruleset_downloader as ruleset_downloader
import sastlib.results_storage as results_storage
from sastlib.plugin_manager import plugin_manager
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
    
    # Determine if any scanner requires full git history
    needs_full_history = plugin_manager.needs_full_git_history(scanners)
    
    log.info(f'Processing task for project: {project_path_with_namespace} with scan_id: {scan_id} with scanners: {scanners}')

    # Get rules directory if any scanner needs it
    rules_dir = None
    requirements = plugin_manager.get_plugin_requirements(scanners)
    needs_rules = any(
        any(req.name == "rules_dir" and req.required for req in reqs)
        for reqs in requirements.values()
    )
    
    if needs_rules:
        rules_dir = sast_ruleset_downloader.get_rules(rule_keys)
        if not rules_dir:
            log.error(f'Failed to download rules for scan_id: {scan_id}')
            exit_with_cleanup()

    use_partial_git_clone = not needs_full_history
    download_result = unified_project_downloader.download_project(project_ssh_url, scan_id, use_partial_git_clone)
    if not download_result:
        log.error(f'Failed to download project sources for scan_id: {scan_id}')
        exit_with_cleanup()
    
    project_sources_dir, project_parent_dir = download_result

    try:
        has_upload_errors = False

        # Run each configured scanner plugin
        for plugin_id in scanners:
            log.info(f'Running {plugin_id} scan')
            
            # Prepare plugin-specific arguments based on requirements
            plugin_kwargs = {}
            plugin = plugin_manager.get_plugin(plugin_id)
            if plugin:
                plugin_requirements = plugin.get_requirements()
                for req in plugin_requirements:
                    if req.name == 'rules_dir' and rules_dir:
                        plugin_kwargs['rules_dir'] = rules_dir
                    elif req.name == 'rule_files' and rule_keys:
                        # Convert rule keys to rule files format for semgrep plugin
                        rule_files = []
                        for rule_key in rule_keys:
                            rule_content = rules_redis.get(rule_key)
                            if rule_content:
                                # Extract rule file name from rule key (format: scan_id:rule_file_path)
                                rule_file_name = rule_key.split(':', 1)[1] if ':' in rule_key else rule_key
                                rule_files.append({
                                    'name': rule_file_name,
                                    'content': rule_content.decode('utf-8') if isinstance(rule_content, bytes) else rule_content
                                })
                        plugin_kwargs['rule_files'] = rule_files
                    # Add other requirement mappings here as needed
            
            # Run the plugin
            results = plugin_manager.run_plugin(
                plugin_id, 
                Path(project_sources_dir), 
                Path(project_parent_dir),
                **plugin_kwargs
            )
            
            if results:
                log.info(f'{plugin_id.capitalize()} results: {results}')
                # Store results in Redis
                store_ok = results_storage.store_scan_results(
                    scans_redis, scan_id, project_url, plugin_id, results
                )
                if not store_ok:
                    log.error(f'Failed to store {plugin_id.capitalize()} results in Redis for scan_id: {scan_id}')
                    has_upload_errors = True
            else:
                log.debug(f'No results for {plugin_id} scan_id: {scan_id}')
        
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
