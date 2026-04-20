from pathlib import Path
from typing import List, Optional, Tuple

from gsast_core.sastlib.plugin_manager import PluginManager


class ScannerService:
    def __init__(self):
        self._plugin_manager = PluginManager()

    def list_scanners(self) -> List[dict]:
        """Return metadata for every registered scanner plugin."""
        scanners = []
        for plugin_id in self._plugin_manager.list_plugins():
            metadata = self._plugin_manager.get_plugin_metadata(plugin_id)
            if metadata:
                scanners.append({
                    'id': metadata['plugin_id'],
                    'name': metadata['name'],
                    'version': metadata['version'],
                    'author': metadata['author'],
                    'description': metadata['description'],
                })
        return scanners

    def get_default_scanners(self) -> List[str]:
        """Return IDs of all available scanner plugins."""
        return self._plugin_manager.get_default_plugins()

    def validate(
        self,
        scanners: List[str],
        rule_files: Optional[list] = None,
        rules_dir: Optional[Path] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate that the requested scanners have their requirements satisfied."""
        return self._plugin_manager.validate_plugin_requirements(
            scanners,
            rule_files=rule_files,
            rules_dir=rules_dir,
        )
