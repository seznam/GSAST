"""
Plugin Management System for GSAST Framework

This module provides dynamic plugin discovery and management through Python entry points.
All plugins run as native Python modules and handle their own subprocess calls if needed.
"""

import importlib.metadata
import json
from typing import Optional, Dict, List
from pathlib import Path

from sastlib.scanner_interface import ScannerInterface
from sastlib.sarif_validator import sarif_validator
from utils.safe_logging import log


class PluginManager:
    """
    Manages scanner plugins through entry points discovery
    
    All plugins run as native Python modules and handle their own subprocess calls if needed.
    Plugins are discovered dynamically at startup via entry points.
    """
    
    ENTRY_POINT_GROUP = "gsast.scanners"
    
    def __init__(self):
        self._plugins: Dict[str, ScannerInterface] = {}
        self._load_plugins()
    
    def _load_plugins(self) -> None:
        """Discover and load all available scanner plugins"""
        log.info("Loading scanner plugins...")
        
        try:
            # Get all entry points for GSAST scanners
            entry_points = importlib.metadata.entry_points()
            
            if hasattr(entry_points, 'select'):
                # Python 3.10+
                scanner_entry_points = entry_points.select(group=self.ENTRY_POINT_GROUP)
            else:
                # Python 3.9
                scanner_entry_points = entry_points.get(self.ENTRY_POINT_GROUP, [])
            
            loaded_count = 0
            for entry_point in scanner_entry_points:
                try:
                    plugin_class = entry_point.load()
                    plugin_instance = plugin_class()
                    
                    if not isinstance(plugin_instance, ScannerInterface):
                        log.error(f"Plugin {entry_point.name} does not implement ScannerInterface")
                        continue
                    
                    plugin_id = plugin_instance.metadata.plugin_id
                    
                    # Validate plugin metadata
                    if plugin_id in self._plugins:
                        log.warning(f"Plugin ID '{plugin_id}' already registered, skipping {entry_point.name}")
                        continue
                    
                    self._plugins[plugin_id] = plugin_instance
                    loaded_count += 1
                    
                    log.info(f"Loaded plugin: {plugin_id} ({plugin_instance.metadata.name}) "
                           f"v{plugin_instance.metadata.version}")
                    
                except Exception as e:
                    log.error(f"Failed to load plugin {entry_point.name}: {e}")
            
            log.info(f"Successfully loaded {loaded_count} scanner plugins")
            
        except Exception as e:
            log.error(f"Failed to discover plugins: {e}")
    
    def get_plugin(self, plugin_id: str) -> Optional[ScannerInterface]:
        """Get a plugin by its unique ID"""
        return self._plugins.get(plugin_id)
    
    def list_plugins(self) -> List[str]:
        """List all available plugin IDs"""
        return list(self._plugins.keys())
    
    def get_default_plugins(self) -> List[str]:
        """Get default plugins to run when none are specified (all available plugins)"""
        return self.list_plugins()
    
    def get_plugin_metadata(self, plugin_id: str) -> Optional[dict]:
        """Get metadata for a specific plugin"""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return None
        
        metadata = plugin.metadata
        return {
            'plugin_id': metadata.plugin_id,
            'name': metadata.name,
            'version': metadata.version,
            'author': metadata.author,
            'description': metadata.description,
        }
    
    def validate_plugin_requirements(self, plugin_ids: List[str], **kwargs) -> tuple[bool, Optional[str]]:
        """
        Validate requirements for a list of plugins
        
        Args:
            plugin_ids: List of plugin IDs to validate
            **kwargs: Parameters to validate against requirements
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        for plugin_id in plugin_ids:
            plugin = self.get_plugin(plugin_id)
            if not plugin:
                return False, f"Unknown plugin: {plugin_id}. Available plugins: {self.list_plugins()}"
            
            is_valid, error_msg = plugin.validate_requirements(**kwargs)
            if not is_valid:
                return False, f"Plugin '{plugin_id}': {error_msg}"
        
        return True, None
    
    def get_plugin_requirements(self, plugin_ids: List[str]) -> Dict[str, List]:
        """
        Get requirements for a list of plugins
        
        Args:
            plugin_ids: List of plugin IDs
            
        Returns:
            Dictionary mapping plugin IDs to their requirements
        """
        requirements = {}
        for plugin_id in plugin_ids:
            plugin = self.get_plugin(plugin_id)
            if plugin:
                requirements[plugin_id] = plugin.get_requirements()
        return requirements
    
    def needs_full_git_history(self, plugin_ids: List[str]) -> bool:
        """
        Check if any of the plugins require full git history
        
        Args:
            plugin_ids: List of plugin IDs to check
            
        Returns:
            True if any plugin requires full git history, False otherwise
        """
        requirements = self.get_plugin_requirements(plugin_ids)
        return any(
            any(req.name == "full_git_history" and req.required for req in reqs)
            for reqs in requirements.values()
        )
    
    def run_plugin(self, plugin_id: str, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        """
        Execute a plugin by ID
        
        Args:
            plugin_id: Unique plugin identifier
            project_sources_dir: Path to project sources
            scan_cwd: Working directory for the scan
            **kwargs: Plugin-specific arguments
            
        Returns:
            Dictionary mapping rule names to SARIF file paths, or None if failed
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            log.error(f'Unknown plugin: {plugin_id}. Available plugins: {self.list_plugins()}')
            return None
        
        # Validate requirements before running
        is_valid, error_msg = plugin.validate_requirements(**kwargs)
        if not is_valid:
            log.error(f'Plugin {plugin_id} requirements not met: {error_msg}')
            return None
        
        try:
            # Run as native Python plugin
            log.info(f'Running plugin: {plugin_id}')
            results = plugin.run_scan(project_sources_dir, scan_cwd, **kwargs)
            
            # Validate SARIF outputs
            if results:
                results = self._validate_and_standardize_sarif_results(results, plugin_id, plugin.metadata)
            
            return results
                
        except Exception as e:
            log.error(f'Plugin {plugin_id} execution failed: {e}', exc_info=True)
            raise e
    
    def _validate_and_standardize_sarif_results(
        self, 
        results: Dict[str, Path], 
        plugin_id: str, 
        plugin_metadata
    ) -> Dict[str, Path]:
        """Validate and standardize SARIF result files"""
        validated_results = {}
        
        # Convert plugin metadata to dict for SARIF validator
        metadata_dict = {
            'plugin_id': plugin_metadata.plugin_id,
            'name': plugin_metadata.name,
            'version': plugin_metadata.version,
            'author': plugin_metadata.author
        }
        
        for rule_name, sarif_file in results.items():
            try:
                # Validate SARIF file
                is_valid, error_msg = sarif_validator.validate_sarif_file(sarif_file)
                
                if not is_valid:
                    log.error(f"SARIF validation failed for {plugin_id} rule '{rule_name}': {error_msg}")
                    continue
                
                # Standardize SARIF output
                try:
                    with open(sarif_file, 'r', encoding='utf-8') as f:
                        sarif_data = json.load(f)
                    
                    standardized_sarif = sarif_validator.standardize_sarif_output(sarif_data, metadata_dict)
                    
                    # Write back standardized SARIF
                    with open(sarif_file, 'w', encoding='utf-8') as f:
                        json.dump(standardized_sarif, f, indent=2)
                    
                    log.debug(f"SARIF standardized for {plugin_id} rule '{rule_name}'")
                    
                except Exception as e:
                    log.warning(f"Failed to standardize SARIF for {plugin_id} rule '{rule_name}': {e}")
                    # Continue with original file even if standardization fails
                
                log.debug(f"SARIF validation passed for {plugin_id} rule '{rule_name}'")
                validated_results[rule_name] = sarif_file
                
            except Exception as e:
                log.error(f"Error validating SARIF file for {plugin_id} rule '{rule_name}': {e}")
                continue
        
        if len(validated_results) != len(results):
            log.warning(f"Some SARIF files failed validation for plugin {plugin_id}")
        
        return validated_results


# Global plugin manager instance
plugin_manager = PluginManager()
