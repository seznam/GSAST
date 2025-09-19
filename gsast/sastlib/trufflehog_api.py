import shutil
import time
import subprocess
from typing import Optional, Dict
from pathlib import Path

from configs.repo_values import GITLAB_URL
from utils.safe_logging import log

from sastlib.results_splitter import trufflehog_to_sarif_and_split_by_source
from sastlib.scanner_utils import run_command


def run_scan(project_sources_dir: Path, scan_cwd: Path) -> Optional[Dict[str, Path]]:
    log.info('Running TruffleHog scan')

    trufflehog = shutil.which('trufflehog')
    if not trufflehog:
        log.error('TruffleHog is not installed')
        return

    scan_start_time = time.time()
    try:
        json_all_results_path = scan_for_secrets(trufflehog, scan_cwd, project_sources_dir)
        sarif_rule_results_paths = trufflehog_to_sarif_and_split_by_source(json_all_results_path)

        log.info(f'TruffleHog scan took {time.time() - scan_start_time} seconds')
        return sarif_rule_results_paths
    except subprocess.CalledProcessError as e:
        log.error(
            f'TruffleHog failed with exit code: {e.returncode}\nstdout:{e.stdout}\nstderr:{e.stderr}'
        )
        raise e


def scan_for_secrets(trufflehog, scan_cwd: Path, project_sources_dir: Path) -> Optional[Path]:
    json_results_path = project_sources_dir / 'trufflehog_results.json'

    trufflehog_args = [
        trufflehog,
        'git',
        f'file://{project_sources_dir}',
        '--only-verified',
        '-j',
        '--verifier',
        f'gitlab={GITLAB_URL}',
        '--no-update',
    ]

    # Inherit SSL and proxy settings from the container environment (Helm chart sets these).
    # Do not override here so we can support both internal GitLab CA and corporate proxy CA bundles.
    result = run_command(trufflehog_args, scan_cwd)

    if not result.stdout:
        return

    with open(json_results_path, 'w') as f:
        f.write(result.stdout)

    return json_results_path

