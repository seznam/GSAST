"""
Semgrep Scanner Plugin for GSAST Framework

This plugin wraps the Semgrep static analysis security scanner.
"""

from typing import Optional, Dict, List
from pathlib import Path

from sastlib.scanner_interface import ScannerInterface, ScannerRequirement, PluginMetadata
from sastlib import semgrep_api
from utils.safe_logging import log


class SemgrepPlugin(ScannerInterface):
    """Semgrep static analysis security scanner plugin"""
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="semgrep",
            name="Semgrep",
            version="1.0.0",
            author="GSAST Team",
            description="Static analysis security scanner using custom and community rules"
        )
    
    def get_requirements(self) -> List[ScannerRequirement]:
        """Semgrep requires rule files to function"""
        return [
            ScannerRequirement(
                name="rule_files",
                required=True,
                description="YAML/JSON rule files for Semgrep static analysis"
            ),
            ScannerRequirement(
                name="rules_dir",
                required=True,
                description="Directory containing extracted rule files"
            )
        ]
    
    def validate_requirements(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate that rule files and rules_dir are provided"""
        rule_files = kwargs.get('rule_files', [])
        rules_dir = kwargs.get('rules_dir')
        
        if not rule_files or not isinstance(rule_files, list):
            return False, "Rule files are required for Semgrep scanner"
        
        if not rules_dir:
            return False, "Rules directory is required for Semgrep scanner"
        
        # Validate rule file format
        for rule_file in rule_files:
            if not isinstance(rule_file, dict):
                return False, "Rule files must be objects with name and content fields"
            if 'name' not in rule_file or 'content' not in rule_file:
                return False, "Rule file must contain 'name' and 'content' fields"
            if not rule_file['name'].endswith(('.yaml', '.yml', '.json')):
                return False, f"Rule file {rule_file['name']} must be in .yaml or .json format"
        
        return True, None
    
    def run_scan(self, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        """Run Semgrep scan with rules"""
        rules_dir = kwargs.get('rules_dir')
        if not rules_dir:
            log.error('Semgrep plugin requires rules_dir argument')
            return None
        
        log.info('Running Semgrep scan via plugin interface')
        return semgrep_api.run_scan(project_sources_dir, scan_cwd, rules_dir)
