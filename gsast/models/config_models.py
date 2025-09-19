"""
Strongly-typed configuration models for GSAST JSON configurations.

This module provides type-safe configuration structures that support both GitHub and GitLab
providers with proper validation and nested access patterns.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, Literal
from enum import Enum
import re
from pathlib import Path
from abc import ABC, abstractmethod


class ProviderType(str, Enum):
    """Supported repository providers."""
    GITHUB = "github"
    GITLAB = "gitlab"


class ScannerType(str, Enum):
    """Supported scanner types."""
    SEMGREP = "semgrep"
    TRUFFLEHOG = "trufflehog"
    DEPENDENCY_CONFUSION = "dependency-confusion"


@dataclass
class TargetConfig(ABC):
    """Base class for target configuration with unified interface."""
    provider: ProviderType
    repositories: Optional[List[str]] = None   # Both providers support repositories
    organizations: Optional[List[str]] = None  # GitHub only
    groups: Optional[List[str]] = None         # GitLab only
    
    def __post_init__(self):
        """Validate base target configuration."""
        # Clean empty lists
        if self.repositories is not None and len(self.repositories) == 0:
            self.repositories = None
        if self.organizations is not None and len(self.organizations) == 0:
            self.organizations = None
        if self.groups is not None and len(self.groups) == 0:
            self.groups = None
        
        # Provider-specific validation
        self.validate_provider_specific()
    
    @abstractmethod
    def validate_provider_specific(self):
        """Validate provider-specific configuration."""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert target configuration to dictionary."""
        result = {'provider': self.provider.value}
        
        if self.repositories:
            result['repositories'] = self.repositories
        if self.organizations:
            result['organizations'] = self.organizations
        if self.groups:
            result['groups'] = self.groups
            
        return result


@dataclass
class GitHubTargetConfig(TargetConfig):
    """GitHub-specific target configuration."""
    
    def __init__(self, organizations: Optional[List[str]] = None, repositories: Optional[List[str]] = None):
        super().__init__(
            provider=ProviderType.GITHUB, 
            repositories=repositories,
            organizations=organizations,
            groups=None  # GitHub doesn't use groups
        )
    
    def validate_provider_specific(self):
        """Validate GitHub target configuration."""
        # GitHub doesn't support groups
        if self.groups is not None:
            raise ValueError("GitHub provider does not support 'groups' field")
        
        # GitHub must specify at least one organization or repository
        if not self.organizations and not self.repositories:
            raise ValueError("GitHub target must specify at least one organization or repository")
        

@dataclass
class GitLabTargetConfig(TargetConfig):
    """GitLab-specific target configuration."""
    
    def __init__(self, groups: Optional[List[str]] = None, repositories: Optional[List[str]] = None):
        super().__init__(
            provider=ProviderType.GITLAB,
            repositories=repositories,
            organizations=None,  # GitLab doesn't use organizations
            groups=groups
        )
    
    def validate_provider_specific(self):
        """Validate GitLab target configuration."""
        # GitLab doesn't support organizations
        if self.organizations is not None:
            raise ValueError("GitLab provider does not support 'organizations' field")


@dataclass
class FiltersConfig:
    """Optional filters configuration."""
    is_archived: Optional[bool] = None
    is_fork: Optional[bool] = None
    is_personal_project: Optional[bool] = None
    max_repo_mb_size: Optional[int] = None
    last_commit_max_age: Optional[int] = None
    ignore_path_regexes: Optional[List[str]] = None
    must_path_regexes: Optional[List[str]] = None
    
    def __post_init__(self):
        """Validate filters configuration."""
        if self.max_repo_mb_size is not None and self.max_repo_mb_size < 0:
            raise ValueError("max_repo_mb_size must be non-negative")
        
        if self.last_commit_max_age is not None and self.last_commit_max_age < 0:
            raise ValueError("last_commit_max_age must be non-negative")
        
        # Validate regex patterns
        if self.ignore_path_regexes:
            for pattern in self.ignore_path_regexes:
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"Invalid regex pattern in ignore_path_regexes: '{pattern}' - {e}")
        
        if self.must_path_regexes:
            for pattern in self.must_path_regexes:
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"Invalid regex pattern in must_path_regexes: '{pattern}' - {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert filters configuration to dictionary."""
        result = {}
        for field_name, field_value in [
            ('is_archived', self.is_archived),
            ('is_fork', self.is_fork),
            ('is_personal_project', self.is_personal_project),
            ('max_repo_mb_size', self.max_repo_mb_size),
            ('last_commit_max_age', self.last_commit_max_age),
            ('ignore_path_regexes', self.ignore_path_regexes),
            ('must_path_regexes', self.must_path_regexes),
        ]:
            if field_value is not None:
                result[field_name] = field_value
        return result


@dataclass
class GSASTConfig:
    """
    Main GSAST configuration structure.
    
    This is the root configuration object that parses the JSON configuration
    and provides strongly-typed access to all configuration sections.
    """
    base_url: str
    target: TargetConfig
    api_secret_key: Optional[str] = None
    filters: Optional[FiltersConfig] = None
    scanners: Optional[List[ScannerType]] = None
    
    def __post_init__(self):
        """Validate the complete configuration."""
        # base_url is mandatory and must be a valid URL format
        if not self.base_url or not self.base_url.strip():
            raise ValueError("base_url is mandatory and cannot be empty")
        
        # Basic URL format validation
        if not (self.base_url.startswith('http://') or self.base_url.startswith('https://')):
            raise ValueError("base_url must start with http:// or https://")
        
        # Clean up scanners list
        if self.scanners is not None and len(self.scanners) == 0:
            self.scanners = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GSASTConfig:
        """
        Create GSASTConfig from a dictionary (typically from JSON).
        
        Args:
            data: Dictionary containing configuration data
            
        Returns:
            GSASTConfig instance
            
        Raises:
            ValueError: If configuration is invalid
            KeyError: If required fields are missing
        """
        # Extract target configuration
        target_data = data.get('target')
        if not target_data:
            raise ValueError("'target' configuration is mandatory")
        
        provider = ProviderType(target_data['provider'])
        
        # Create provider-specific target configuration
        if provider == ProviderType.GITHUB:
            target_config = GitHubTargetConfig(
                organizations=target_data.get('organizations'),
                repositories=target_data.get('repositories')
            )
        else:  # GitLab
            target_config = GitLabTargetConfig(
                groups=target_data.get('groups'),
                repositories=target_data.get('repositories')
            )
        
        # Extract filters configuration (optional)
        filters_config = None
        if 'filters' in data:
            filters_data = data['filters']
            filters_config = FiltersConfig(
                is_archived=filters_data.get('is_archived'),
                is_fork=filters_data.get('is_fork'),
                is_personal_project=filters_data.get('is_personal_project'),
                max_repo_mb_size=filters_data.get('max_repo_mb_size'),
                last_commit_max_age=filters_data.get('last_commit_max_age'),
                ignore_path_regexes=filters_data.get('ignore_path_regexes'),
                must_path_regexes=filters_data.get('must_path_regexes')
            )
        
        # Extract scanners configuration (optional)
        scanners = None
        if 'scanners' in data and data['scanners']:
            scanners = [ScannerType(scanner) for scanner in data['scanners']]

        
        return cls(
            api_secret_key=data.get('api_secret_key'),
            base_url=data['base_url'],
            target=target_config,
            filters=filters_config,
            scanners=scanners,
        )
    
    @classmethod
    def from_json_file(cls, file_path: Union[str, Path]) -> GSASTConfig:
        """
        Load configuration from a JSON file.
        
        Args:
            file_path: Path to the JSON configuration file
            
        Returns:
            GSASTConfig instance
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If JSON is invalid or configuration is invalid
        """
        import json
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        
        return cls.from_dict(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration back to dictionary format.
        
        Returns:
            Dictionary representation of the configuration
        """
        result = {
            'base_url': self.base_url,
            'target': self.target.to_dict()
        }
        
        # Add optional api_secret_key
        if self.api_secret_key is not None:
            result['api_secret_key'] = self.api_secret_key
        
        # Add optional sections
        if self.filters:
            filters_dict = self.filters.to_dict()
            if filters_dict:
                result['filters'] = filters_dict
        
        if self.scanners:
            result['scanners'] = [scanner.value for scanner in self.scanners]
        
        return result
    
    def get_target_for_provider(self) -> TargetConfig:
        """
        Get provider-specific target configuration.
        
        Returns:
            Provider-specific target configuration object
        """
        return self.target 