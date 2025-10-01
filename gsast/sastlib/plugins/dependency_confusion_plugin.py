"""
Dependency Confusion Scanner Plugin for GSAST Framework

This plugin wraps the Dependency Confusion attack detection scanner.
"""

from typing import Optional, Dict, List
from pathlib import Path

from sastlib.scanner_interface import ScannerInterface, ScannerRequirement, PluginMetadata
from sastlib import dependency_confusion_api
from utils.safe_logging import log


class DependencyConfusionPlugin(ScannerInterface):
    """Dependency confusion attack detection scanner plugin"""
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="dependency-confusion",
            name="Dependency Confusion Scanner",
            version="1.0.0",
            author="GSAST Team",
            description="Detects potential dependency confusion vulnerabilities in package manifests"
        )
    
    def get_requirements(self) -> List[ScannerRequirement]:
        """Dependency confusion scanner has no special requirements"""
        return []
    
    def validate_requirements(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Dependency confusion scanner has no special requirements to validate"""
        return True, None
    
    def run_scan(self, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        """Run dependency confusion scan"""
        log.info('Running Dependency Confusion scan via plugin interface')
        return dependency_confusion_api.run_scan(project_sources_dir, scan_cwd)
