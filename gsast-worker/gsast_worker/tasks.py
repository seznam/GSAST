import os
import sys
import shutil
from pathlib import Path

from gsast_core.repolib import UnifiedProjectDownloader
import gsast_core.sastlib.results_storage as results_storage
import gsast_core.sastlib.ruleset_downloader as ruleset_downloader
from gsast_core.sastlib.plugin_manager import plugin_manager
from gsast_core.utils.safe_logging import log

_ctx: dict | None = None


def init_ctx(scans_redis, rules_redis, unified_project_downloader, sast_ruleset_downloader):
    """Called once by worker.py at startup to wire process-level resources."""
    global _ctx
    _ctx = {
        'scans_redis': scans_redis,
        'rules_redis': rules_redis,
        'unified_project_downloader': unified_project_downloader,
        'sast_ruleset_downloader': sast_ruleset_downloader,
    }


def _get_ctx() -> dict:
    if _ctx is None:
        raise RuntimeError('Worker context not initialized. Call init_ctx() at startup.')
    return _ctx


def exit_with_cleanup(project_sources_dir=None):
    if project_sources_dir and os.path.exists(project_sources_dir):
        shutil.rmtree(project_sources_dir)
    sys.exit(1)


def process_task(scan_id, project_ssh_url, rule_keys, scanners, project_url=None):
    ctx = _get_ctx()
    scans_redis = ctx['scans_redis']
    rules_redis = ctx['rules_redis']
    unified_project_downloader: UnifiedProjectDownloader = ctx['unified_project_downloader']
    sast_ruleset_downloader: ruleset_downloader.RulesetDownloader = ctx['sast_ruleset_downloader']

    project_path_with_namespace = unified_project_downloader.get_project_path(project_ssh_url)

    needs_full_history = plugin_manager.needs_full_git_history(scanners)

    log.info(f'Processing task for project: {project_path_with_namespace} with scan_id: {scan_id} with scanners: {scanners}')

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

        for plugin_id in scanners:
            log.info(f'Running {plugin_id} scan')

            plugin_kwargs = {}
            plugin = plugin_manager.get_plugin(plugin_id)
            if plugin:
                plugin_requirements = plugin.get_requirements()
                for req in plugin_requirements:
                    if req.name == 'rules_dir' and rules_dir:
                        plugin_kwargs['rules_dir'] = rules_dir
                    elif req.name == 'rule_files' and rule_keys:
                        rule_files = []
                        for rule_key in rule_keys:
                            rule_content = rules_redis.get(rule_key)
                            if rule_content:
                                rule_file_name = rule_key.split(':', 1)[1] if ':' in rule_key else rule_key
                                rule_files.append({
                                    'name': rule_file_name,
                                    'content': rule_content.decode('utf-8') if isinstance(rule_content, bytes) else rule_content,
                                })
                        plugin_kwargs['rule_files'] = rule_files

            results = plugin_manager.run_plugin(
                plugin_id,
                Path(project_sources_dir),
                Path(project_parent_dir),
                **plugin_kwargs,
            )

            if results:
                log.info(f'{plugin_id.capitalize()} results: {results}')
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
