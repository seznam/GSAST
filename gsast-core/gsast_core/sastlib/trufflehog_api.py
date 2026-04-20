import os
import shutil
import time
import subprocess
from typing import Optional, Dict
from pathlib import Path

from gsast_core.configs.repo_values import GITLAB_URL, GITHUB_URL
from gsast_core.utils.safe_logging import log

from gsast_core.sastlib.results_splitter import trufflehog_to_sarif_and_split_by_source
from gsast_core.sastlib.scanner_utils import run_command

CUSTOM_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'configs' / 'trufflehog_config.yaml'
ONLY_VERIFIED = os.getenv('TRUFFLEHOG_ONLY_VERIFIED', 'true').lower() == 'true'


def run_scan(project_sources_dir: Path, scan_cwd: Path) -> Optional[Dict[str, Path]]:
    log.info('Running TruffleHog scan')

    trufflehog = shutil.which('trufflehog')
    if not trufflehog:
        log.error('TruffleHog is not installed')
        return None

    scan_start_time = time.time()
    try:
        json_all_results_path = scan_for_secrets(trufflehog, scan_cwd, project_sources_dir)
        sarif_rule_results_paths = trufflehog_to_sarif_and_split_by_source(json_all_results_path)

        log.info(f'TruffleHog scan took {time.time() - scan_start_time} seconds')
        return sarif_rule_results_paths
    except subprocess.CalledProcessError as e:
        log.error(
            f'TruffleHog failed with exit code: {e.returncode}\nstdout: {e.stdout}\nstderr: {e.stderr}'
        )
        return None


def scan_for_secrets(trufflehog, scan_cwd: Path, project_sources_dir: Path) -> Optional[Path]:
    json_results_path = project_sources_dir / 'trufflehog_results.json'

    trufflehog_args = [
        trufflehog,
        'git',
        f'file://{project_sources_dir}',
        '-j',
        '--verifier',
        f'github={GITHUB_URL}' if (project_sources_dir / '.github').exists() else f'gitlab={GITLAB_URL}',
        '--no-update',
    ]

    if ONLY_VERIFIED:
        trufflehog_args.append('--only-verified')
        log.debug('TruffleHog will report only verified secrets')
    else:
        log.debug('TruffleHog will report all secrets (verified and unverified)')

    if CUSTOM_CONFIG_PATH.exists():
        trufflehog_args.extend(['--config', str(CUSTOM_CONFIG_PATH)])
        log.debug(f'Using custom TruffleHog config: {CUSTOM_CONFIG_PATH}')
    else:
        log.debug('No custom TruffleHog config found, using built-in detectors only')

    # Inherit SSL and proxy settings from the container environment (Helm chart sets these).
    # Do not override here so we can support both internal GitLab CA and corporate proxy CA bundles.
    # Note: TruffleHog may exit with code 1 for various reasons (no findings, not a git repo, etc.)
    # We use subprocess.run directly instead of run_command to handle this more gracefully
    log.debug(f'Running command: {trufflehog_args} in dir: {scan_cwd.absolute()}')
    result = subprocess.run(
        trufflehog_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=scan_cwd,
    )

    log.debug(f'TruffleHog exited with code: {result.returncode}')

    # Check for actual errors (not just exit code 1 which can be normal)
    if result.returncode != 0:
        # Log the stderr for debugging
        if result.stderr:
            log.warning(f'TruffleHog stderr: {result.stderr}')

        # If exit code is not 0 or 1, or if there's critical error messages, raise exception
        if result.returncode > 1 or (result.stderr and ('fatal' in result.stderr.lower() or 'error' in result.stderr.lower())):
            raise subprocess.CalledProcessError(
                result.returncode,
                trufflehog_args,
                output=result.stdout,
                stderr=result.stderr
            )

        # Exit code 1 with no critical errors is acceptable (likely no findings)
        log.debug(f'TruffleHog exit code {result.returncode} is acceptable (likely no findings)')

    if not result.stdout or not result.stdout.strip():
        log.info('TruffleHog found no secrets')
        return None

    with open(json_results_path, 'w') as f:
        f.write(result.stdout)

    return json_results_path
