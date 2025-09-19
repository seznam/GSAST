import json
import tempfile
import time
from typing import Optional, Dict
from pathlib import Path

from utils.safe_logging import log
from sastlib.results_splitter import split_sarif_by_rules

# Import the external dependency confusion scanner
try:
    import confusion_hunter as dep_conf
except ImportError:
    # Fallback error message with helpful instructions
    raise ImportError(
        "confusion-hunter package not found. Please install it with: pip install confusion-hunter"
    )


def run_scan(project_sources_dir: Path, scan_cwd: Path) -> Optional[Dict[str, Path]]:
    """
    Run dependency confusion scan on the project
    
    Args:
        project_sources_dir: Path to the project sources
        scan_cwd: Path to the working directory for the scan
        
    Returns:
        Dictionary mapping rule names to SARIF file paths, or None if no results
    """
    log.info('Running Dependency Confusion scan on %s', project_sources_dir)
    
    scan_start_time = time.time()
    try:
        log.info('Dependency Confusion: Setting up scanner')
        # Setup and run the dependency confusion scanner
        scanner = dep_conf.setup_scanner(project_root=str(project_sources_dir))
        
        log.info('Dependency Confusion: Scan of the whole repository')
        # Run scan of the whole repository
        findings = scanner.find_config_files()
        
        log.info('Dependency Confusion: Scan based on the findings')
        # Run scan based on the findings
        unclaimed_packages = scanner.scan_files(findings)
        
        # Format the resulting data
        results = dep_conf.ScanResult(findings=findings, unclaimed_packages=unclaimed_packages)
        
        if not results.unclaimed_packages:
            log.debug('No dependency confusion vulnerabilities found')
            return None
        
        # Create SARIF file and write results to it
        sarif_results_path = project_sources_dir / '.dependency_confusion_results.sarif'
        sarif_data = results.to_sarif()
        
        with open(sarif_results_path, 'w') as f:
            json.dump(sarif_data, f, indent=2)
        
        # Split SARIF by rules (scan types)
        sarif_rule_results_paths = split_sarif_by_rules(sarif_results_path)
        
        log.info(f'Dependency Confusion scan took {time.time() - scan_start_time} seconds')
        log.info(f'Found {len(results.unclaimed_packages)} unclaimed packages')
        
        return sarif_rule_results_paths
        
    except Exception as e:
        log.error(f'Dependency Confusion scan failed: {e}', exc_info=True)
        raise e