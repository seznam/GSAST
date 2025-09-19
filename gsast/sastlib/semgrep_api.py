import os
import shutil
import time
import subprocess
from typing import Optional, Dict
from pathlib import Path

from utils.safe_logging import log

from sastlib.results_splitter import split_sarif_by_rules
from sastlib.scanner_utils import run_command


def run_scan(project_sources_dir: Path, scan_cwd: Path, rules_dir: Path) -> Optional[Dict[str, Path]]:
    log.info('Running Semgrep scan')

    semgrep = shutil.which('semgrep')
    if not semgrep:
        log.error('Semgrep is not installed')
        return

    scan_start_time = time.time()
    try:
        sarif_all_results_path = scan_for_rules(semgrep, scan_cwd, project_sources_dir, rules_dir)
        sarif_rule_results_paths = split_sarif_by_rules(sarif_all_results_path)

        log.info(f'Semgrep scan took {time.time() - scan_start_time} seconds')
        return sarif_rule_results_paths

    except subprocess.CalledProcessError as e:
        log.error(
            f'Semgrep failed with exit code: {e.returncode}\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}'
        )
        raise e


def scan_for_rules(semgrep, scan_cwd: Path, project_sources_dir: Path, rules_dir: Path) -> Path:
    sarif_results_path = project_sources_dir / '.semgrep_results.sarif'

    # Create soft links to the files and dirs of rules directory in the cwd directory
    # This is needed since otherwise semgrep will include the tmp directory name in the sarif results
    rules_paths = []
    for rules_dir_item in rules_dir.iterdir():
        if rules_dir_item.is_dir() or rules_dir_item.is_file():
            os.symlink(rules_dir_item, scan_cwd / rules_dir_item.name)
            rules_paths.append(rules_dir_item.name)

    semgrep_args = [
        semgrep,
        'scan',
        '--sarif',
        '--metrics',
        'off',
        '--max-target-bytes',
        '10000000',
        '--exclude="*.html"',
        '--timeout=900',
        *[f'--config={rule_path}' for rule_path in rules_paths],
        str(project_sources_dir.relative_to(scan_cwd)),
    ]

    result = run_command(semgrep_args, scan_cwd)

    with open(sarif_results_path, 'w') as f:
        f.write(result.stdout)

    return sarif_results_path
