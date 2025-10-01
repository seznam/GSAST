from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from pathlib import Path
from dataclasses import dataclass


class ScannerRequirement:
    """Describes a requirement for a scanner"""
    
    def __init__(self, name: str, required: bool = True, description: str = ""):
        self.name = name
        self.required = required
        self.description = description


@dataclass
class PluginMetadata:
    """Metadata describing a scanner plugin"""
    plugin_id: str  # Unique stable identifier (e.g., "semgrep", "trufflehog")
    name: str  # Human-readable name
    version: str  # Plugin version
    author: str  # Plugin author/organization
    description: str  # Brief description of what the scanner does


class ScannerInterface(ABC):
    """Abstract base class for all security scanners"""
    
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata including unique ID, version, and author"""
        pass
    
    @property
    def name(self) -> str:
        """Return the scanner name (backward compatibility)"""
        return self.metadata.plugin_id
    
    @abstractmethod
    def get_requirements(self) -> List[ScannerRequirement]:
        """
        Return list of requirements for this scanner
        
        Returns:
            List of ScannerRequirement objects describing what the scanner needs
        """
        pass
    
    @abstractmethod
    def validate_requirements(self, **kwargs) -> tuple[bool, Optional[str]]:
        """
        Validate that all required parameters are provided
        
        Args:
            **kwargs: Parameters to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    def run_scan(self, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        """
        Run the security scan
        
        Args:
            project_sources_dir: Path to the project sources
            scan_cwd: Path to the working directory for the scan
            **kwargs: Additional scanner-specific arguments
            
        Returns:
            Dictionary mapping rule names to SARIF file paths, or None if no results
        """
        pass
