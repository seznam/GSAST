from abc import ABC, abstractmethod
from typing import Optional, Tuple
from pathlib import Path, PurePath


class BaseRepositoryDownloader(ABC):
    """Abstract base class for project downloaders."""
    
    @abstractmethod
    def __init__(self, **kwargs):
        """Initialize the downloader with platform-specific parameters."""
        pass
    
    @abstractmethod
    def download_project(self, project_url: str, project_parent_dir_name: str, use_shallow_clone: bool = True) -> Optional[Tuple[Path, Path]]:
        """
        Download a project to a temporary location.
        Returns tuple of (project_dir, project_parent_dir) or None if failed.
        """
        pass
    
    @abstractmethod
    def download_to_permanent_location(self, project_url: str, destination_dir: Path, use_shallow_clone: bool = True, flat_structure: bool = False) -> Optional[Path]:
        """
        Download project directly to a permanent location.
        Returns the final project directory path or None if failed.
        """
        pass
    
    @abstractmethod
    def get_project_path(self, project_url: str) -> PurePath:
        """Extract project path from URL (e.g., 'owner/repo')."""
        pass
    
    def __del__(self):
        """Cleanup method - should be implemented by subclasses if needed."""
        pass 
