"""
Trufflehog Scanner Plugin for GSAST Framework

This plugin wraps the Trufflehog secrets detection scanner.
"""

from typing import Optional, Dict, List
from pathlib import Path

from sastlib.scanner_interface import ScannerInterface, ScannerRequirement, PluginMetadata
from sastlib import trufflehog_api
from utils.safe_logging import log


class TrufflehogPlugin(ScannerInterface):
    """Trufflehog secrets detection scanner plugin"""
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="trufflehog",
            name="Trufflehog",
            version="1.0.0",
            author="GSAST Team",
            description="Git repository secrets scanner that detects credentials and API keys"
        )
    
    def get_requirements(self) -> List[ScannerRequirement]:
        """Trufflehog requires full git history to scan for secrets"""
        return [
            ScannerRequirement(
                name="full_git_history",
                required=True,
                description="Full git history required for scanning secrets in commit history"
            )
        ]
    
    def validate_requirements(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Trufflehog has no special requirements to validate"""
        return True, None
    
    def run_scan(self, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        """Run Trufflehog scan for secrets"""
        log.info('Running Trufflehog scan via plugin interface')
        return trufflehog_api.run_scan(project_sources_dir, scan_cwd)
