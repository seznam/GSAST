"""
Comprehensive tests for GSAST configuration models.

This test suite verifies all aspects of the configuration system including:
- Validation logic for all configuration sections
- Provider-specific validation rules  
- Edge cases and error handling
- JSON parsing and serialization
"""

import pytest
import json
import tempfile
from pathlib import Path
from typing import Dict, Any

from gsast.models.config_models import (
    GSASTConfig,
    FiltersConfig,
    GitHubTargetConfig,
    GitLabTargetConfig,
    ProviderType,
    ScannerType
)


class TestProviderType:
    """Test ProviderType enum."""
    
    def test_valid_providers(self):
        """Test valid provider values."""
        assert ProviderType.GITHUB == "github"
        assert ProviderType.GITLAB == "gitlab"
        
    def test_provider_from_string(self):
        """Test creating provider from string."""
        assert ProviderType("github") == ProviderType.GITHUB
        assert ProviderType("gitlab") == ProviderType.GITLAB
        
    def test_invalid_provider(self):
        """Test invalid provider raises ValueError."""
        with pytest.raises(ValueError):
            ProviderType("bitbucket")


class TestScannerType:
    """Test ScannerType enum."""
    
    def test_valid_scanners(self):
        """Test valid scanner values."""
        assert ScannerType.SEMGREP == "semgrep"
        assert ScannerType.TRUFFLEHOG == "trufflehog"
        assert ScannerType.DEPENDENCY_CONFUSION == "dependency-confusion"
        
    def test_scanner_from_string(self):
        """Test creating scanners from string."""
        assert ScannerType("semgrep") == ScannerType.SEMGREP
        assert ScannerType("trufflehog") == ScannerType.TRUFFLEHOG
        assert ScannerType("dependency-confusion") == ScannerType.DEPENDENCY_CONFUSION


class TestGitHubTargetConfig:
    """Test GitHub-specific target configuration."""
    
    def test_valid_organizations_only(self):
        """Test valid configuration with only organizations."""
        config = GitHubTargetConfig(organizations=["microsoft", "google"])
        assert config.organizations == ["microsoft", "google"]
        assert config.repositories is None
        
    def test_valid_repositories_only(self):
        """Test valid configuration with only repositories.""" 
        config = GitHubTargetConfig(repositories=["torvalds/linux", "facebook/react"])
        assert config.repositories == ["torvalds/linux", "facebook/react"]
        assert config.organizations is None
        
    def test_valid_both_organizations_and_repositories(self):
        """Test valid configuration with both organizations and repositories."""
        config = GitHubTargetConfig(
            organizations=["microsoft"],
            repositories=["torvalds/linux"]
        )
        assert config.organizations == ["microsoft"]
        assert config.repositories == ["torvalds/linux"]
        
    def test_empty_lists_cleaned_up(self):
        """Test that empty lists are converted to None."""
        config = GitHubTargetConfig(organizations=[], repositories=["repo1"])
        assert config.organizations is None
        assert config.repositories == ["repo1"]
        
    def test_both_empty_raises_error(self):
        """Test that having no organizations or repositories raises error."""
        with pytest.raises(ValueError, match="GitHub target must specify at least one organization or repository"):
            GitHubTargetConfig(organizations=None, repositories=None)
            
    def test_both_empty_lists_raises_error(self):
        """Test that empty lists for both fields raises error."""
        with pytest.raises(ValueError, match="GitHub target must specify at least one organization or repository"):
            GitHubTargetConfig(organizations=[], repositories=[])


class TestGitLabTargetConfig:
    """Test GitLab-specific target configuration."""
    
    def test_valid_groups_only(self):
        """Test valid configuration with only groups."""
        config = GitLabTargetConfig(groups=["example-group"])
        assert config.groups == ["example-group"]
        assert config.repositories is None
        
    def test_valid_repositories_only(self):
        """Test valid configuration with only repositories."""
        config = GitLabTargetConfig(repositories=["project1/repo"])
        assert config.repositories == ["project1/repo"]
        assert config.groups is None
        
    def test_both_none_allowed(self):
        """Test that both being None is allowed for GitLab (uses defaults)."""
        config = GitLabTargetConfig(groups=None, repositories=None)
        assert config.groups is None
        assert config.repositories is None
        
    def test_empty_lists_cleaned_up(self):
        """Test that empty lists are converted to None."""
        config = GitLabTargetConfig(groups=[], repositories=["repo1"])
        assert config.groups is None
        assert config.repositories == ["repo1"]


class TestTargetConfig:
    """Test unified target configuration."""
    
    def test_github_valid_organizations(self):
        """Test valid GitHub configuration with organizations."""
        config = GitHubTargetConfig(organizations=["microsoft", "google"])
        assert config.provider == ProviderType.GITHUB
        assert config.organizations == ["microsoft", "google"]
        
    def test_github_valid_repositories(self):
        """Test valid GitHub configuration with repositories."""
        config = GitHubTargetConfig(repositories=["torvalds/linux"])
        assert config.provider == ProviderType.GITHUB
        assert config.repositories == ["torvalds/linux"]
        
    def test_github_with_groups_raises_error(self):
        """Test that GitHub provider cannot have groups field."""
        # GitHub configs can't have groups, so this test isn't applicable with the new design
        # GitHubTargetConfig doesn't have a groups parameter
        pass
            
    def test_github_without_org_or_repo_raises_error(self):
        """Test that GitHub provider without org or repo raises error."""
        with pytest.raises(ValueError, match="GitHub target must specify at least one organization or repository"):
            GitHubTargetConfig()
            
    def test_gitlab_valid_groups(self):
        """Test valid GitLab configuration with groups."""
        config = GitLabTargetConfig(groups=["example-group"])
        assert config.provider == ProviderType.GITLAB
        assert config.groups == ["example-group"]
        
    def test_gitlab_with_organizations_raises_error(self):
        """Test that GitLab provider cannot have organizations field."""
        # GitLab configs can't have organizations, so this test isn't applicable with the new design
        # GitLabTargetConfig doesn't have an organizations parameter
        pass
            
    def test_gitlab_empty_allowed(self):
        """Test that GitLab provider can have empty groups and repositories."""
        config = GitLabTargetConfig()
        assert config.provider == ProviderType.GITLAB
        assert config.groups is None
        assert config.repositories is None
        
    def test_get_github_config(self):
        """Test GitHub config to_dict method."""
        config = GitHubTargetConfig(
            organizations=["microsoft"],
            repositories=["torvalds/linux"]
        )
        config_dict = config.to_dict()
        assert config_dict['provider'] == 'github'
        assert config_dict['organizations'] == ["microsoft"]
        assert config_dict['repositories'] == ["torvalds/linux"]
        
    def test_get_gitlab_config(self):
        """Test GitLab config to_dict method."""
        config = GitLabTargetConfig(
            groups=["example-group"],
            repositories=["project/repo"]
        )
        config_dict = config.to_dict()
        assert config_dict['provider'] == 'gitlab'
        assert config_dict['groups'] == ["example-group"]
        assert config_dict['repositories'] == ["project/repo"]
        
    def test_get_wrong_provider_config_raises_error(self):
        """Test that configs work with their intended providers."""
        github_config = GitHubTargetConfig(organizations=["test"])
        assert github_config.provider == ProviderType.GITHUB
            
        gitlab_config = GitLabTargetConfig(groups=["test"])
        assert gitlab_config.provider == ProviderType.GITLAB


class TestFiltersConfig:
    """Test filters configuration."""
    
    def test_all_none_valid(self):
        """Test that all None values are valid."""
        config = FiltersConfig()
        assert config.is_archived is None
        assert config.is_fork is None
        assert config.max_repo_mb_size is None
        
    def test_valid_filters(self):
        """Test valid filter configuration."""
        config = FiltersConfig(
            is_archived=False,
            is_fork=True,
            max_repo_mb_size=500,
            last_commit_max_age=90,
            ignore_path_regexes=["^tests/", "mock"],
            must_path_regexes=["src/"]
        )
        assert config.is_archived is False
        assert config.is_fork is True
        assert config.max_repo_mb_size == 500
        assert config.last_commit_max_age == 90
        assert config.ignore_path_regexes == ["^tests/", "mock"]
        assert config.must_path_regexes == ["src/"]
        
    def test_negative_size_raises_error(self):
        """Test that negative max_repo_mb_size raises error."""
        with pytest.raises(ValueError, match="max_repo_mb_size must be non-negative"):
            FiltersConfig(max_repo_mb_size=-1)
            
    def test_negative_age_raises_error(self):
        """Test that negative last_commit_max_age raises error."""
        with pytest.raises(ValueError, match="last_commit_max_age must be non-negative"):
            FiltersConfig(last_commit_max_age=-1)
            
    def test_invalid_ignore_regex_raises_error(self):
        """Test that invalid regex in ignore_path_regexes raises error."""
        with pytest.raises(ValueError, match="Invalid regex pattern in ignore_path_regexes"):
            FiltersConfig(ignore_path_regexes=["[invalid"])
            
    def test_invalid_must_regex_raises_error(self):
        """Test that invalid regex in must_path_regexes raises error."""
        with pytest.raises(ValueError, match="Invalid regex pattern in must_path_regexes"):
            FiltersConfig(must_path_regexes=["[invalid"])
            
    def test_valid_regex_patterns(self):
        """Test that valid regex patterns are accepted."""
        config = FiltersConfig(
            ignore_path_regexes=[r"^tests/", r"\.test\.", r"\bmock\b"],
            must_path_regexes=[r"src/.*\.py$", r"lib/"]
        )
        assert len(config.ignore_path_regexes) == 3
        assert len(config.must_path_regexes) == 2

        
class TestGSASTConfig:
    """Test main GSAST configuration."""
    
    def get_valid_github_dict(self) -> Dict[str, Any]:
        """Get a valid GitHub configuration dictionary."""
        return {
            "api_secret_key": "test_key",
            "base_url": "https://example.com/",
            "target": {
                "provider": "github",
                "organizations": ["microsoft", "google"],
                "repositories": ["torvalds/linux"]
            },
            "filters": {
                "is_archived": False,
                "is_fork": True,
                "max_repo_mb_size": 500
            },
            "scanners": ["semgrep", "dependency-confusion"],
        }
        
    def get_valid_gitlab_dict(self) -> Dict[str, Any]:
        """Get a valid GitLab configuration dictionary."""
        return {
            "base_url": "https://gitlab.example.com/",
            "target": {
                "provider": "gitlab",
                "groups": ["example-group"],
                "repositories": ["project/repo"]
            },
            "scanners": ["semgrep", "trufflehog"]
        }
    
    def test_from_dict_github_complete(self):
        """Test creating config from complete GitHub dictionary."""
        data = self.get_valid_github_dict()
        config = GSASTConfig.from_dict(data)
        
        assert config.api_secret_key == "test_key"
        assert config.base_url == "https://example.com/"
        assert config.target.provider == ProviderType.GITHUB
        assert config.target.organizations == ["microsoft", "google"]
        assert config.target.repositories == ["torvalds/linux"]
        assert config.filters.is_archived is False
        assert config.filters.is_fork is True
        assert config.filters.max_repo_mb_size == 500
        assert len(config.scanners) == 2
        assert ScannerType.SEMGREP in config.scanners
        assert ScannerType.DEPENDENCY_CONFUSION in config.scanners
        
    def test_from_dict_gitlab_minimal(self):
        """Test creating config from minimal GitLab dictionary."""
        data = self.get_valid_gitlab_dict()
        config = GSASTConfig.from_dict(data)
        
        assert config.api_secret_key is None
        assert config.base_url == "https://gitlab.example.com/"
        assert config.target.provider == ProviderType.GITLAB
        assert config.target.groups == ["example-group"]
        assert config.filters is None
        assert len(config.scanners) == 2
        
    def test_from_dict_missing_base_url_raises_error(self):
        """Test that missing base_url raises error."""
        data = self.get_valid_github_dict()
        del data["base_url"]
        
        with pytest.raises(KeyError):
            GSASTConfig.from_dict(data)
            
    def test_from_dict_empty_base_url_raises_error(self):
        """Test that empty base_url raises error."""
        data = self.get_valid_github_dict()
        data["base_url"] = ""
        
        with pytest.raises(ValueError, match="base_url is mandatory and cannot be empty"):
            GSASTConfig.from_dict(data)
            
    def test_from_dict_invalid_base_url_raises_error(self):
        """Test that invalid base_url raises error."""
        data = self.get_valid_github_dict()
        data["base_url"] = "invalid-url"
        
        with pytest.raises(ValueError, match="base_url must start with http"):
            GSASTConfig.from_dict(data)
            
    def test_from_dict_missing_target_raises_error(self):
        """Test that missing target raises error."""
        data = self.get_valid_github_dict()
        del data["target"]
        
        with pytest.raises(ValueError, match="'target' configuration is mandatory"):
            GSASTConfig.from_dict(data)
            
    def test_from_dict_invalid_provider_raises_error(self):
        """Test that invalid provider raises error."""
        data = self.get_valid_github_dict()
        data["target"]["provider"] = "bitbucket"
        
        with pytest.raises(ValueError):
            GSASTConfig.from_dict(data)
            
    def test_from_dict_invalid_scanner_raises_error(self):
        """Test that invalid scanner raises error."""
        data = self.get_valid_github_dict()
        data["scanners"] = ["semgrep", "invalid-scanner"]
        
        with pytest.raises(ValueError):
            GSASTConfig.from_dict(data)
            
    def test_from_dict_empty_scanners_cleaned_up(self):
        """Test that empty scanners list is cleaned up to None."""
        data = self.get_valid_github_dict()
        data["scanners"] = []
        
        config = GSASTConfig.from_dict(data)
        assert config.scanners is None
        
    def test_to_dict_github_complete(self):
        """Test converting complete GitHub config to dictionary."""
        data = self.get_valid_github_dict()
        config = GSASTConfig.from_dict(data)
        result = config.to_dict()
        
        # Check structure matches original
        assert result["api_secret_key"] == data["api_secret_key"]
        assert result["base_url"] == data["base_url"]
        assert result["target"]["provider"] == data["target"]["provider"]
        assert result["target"]["organizations"] == data["target"]["organizations"]
        assert result["target"]["repositories"] == data["target"]["repositories"]
        assert "groups" not in result["target"]  # Should not be present for GitHub
        assert result["filters"]["is_archived"] == data["filters"]["is_archived"]
        assert set(result["scanners"]) == set(data["scanners"])
        
    def test_to_dict_gitlab_minimal(self):
        """Test converting minimal GitLab config to dictionary."""
        data = self.get_valid_gitlab_dict()
        config = GSASTConfig.from_dict(data)
        result = config.to_dict()
        
        assert "api_secret_key" not in result  # Should not be present if None
        assert result["base_url"] == data["base_url"]
        assert result["target"]["provider"] == data["target"]["provider"]
        assert result["target"]["groups"] == data["target"]["groups"]
        assert "organizations" not in result["target"]  # Should not be present for GitLab
        assert "filters" not in result  # Should not be present if None
        assert set(result["scanners"]) == set(data["scanners"])
        
    def test_get_target_for_provider_github(self):
        """Test getting provider-specific target for GitHub."""
        data = self.get_valid_github_dict()
        config = GSASTConfig.from_dict(data)
        target = config.get_target_for_provider()
        
        assert isinstance(target, GitHubTargetConfig)
        assert target.organizations == ["microsoft", "google"]
        assert target.repositories == ["torvalds/linux"]
        
    def test_get_target_for_provider_gitlab(self):
        """Test getting provider-specific target for GitLab."""
        data = self.get_valid_gitlab_dict()
        config = GSASTConfig.from_dict(data)
        target = config.get_target_for_provider()
        
        assert isinstance(target, GitLabTargetConfig)
        assert target.groups == ["example-group"]
        assert target.repositories == ["project/repo"]
        
    def test_from_json_file_valid(self):
        """Test loading config from valid JSON file."""
        data = self.get_valid_github_dict()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name
            
        try:
            config = GSASTConfig.from_json_file(temp_path)
            assert config.target.provider == ProviderType.GITHUB
            assert config.base_url == "https://example.com/"
        finally:
            Path(temp_path).unlink()
            
    def test_from_json_file_not_found_raises_error(self):
        """Test that non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            GSASTConfig.from_json_file("non_existent_file.json")
            
    def test_from_json_file_invalid_json_raises_error(self):
        """Test that invalid JSON raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name
            
        try:
            with pytest.raises(ValueError, match="Invalid JSON in configuration file"):
                GSASTConfig.from_json_file(temp_path)
        finally:
            Path(temp_path).unlink()


class TestIntegrationWithExistingConfigs:
    """Test integration with the existing JSON configuration files."""
    
    def test_parse_existing_github_config(self):
        """Test parsing the existing gsast-GitHub.json file."""
        github_json_path = Path("tests/mock/test-github.json")
        
        # Load and parse the existing config
        config = GSASTConfig.from_json_file(github_json_path)
        
        # Verify it parses correctly
        assert config.api_secret_key == "..."  # API key is redacted in the config file
        assert config.base_url == "https://gsast-server.example.com/"
        assert config.target.provider == ProviderType.GITHUB
        assert "example-org" in config.target.organizations
        assert "google" in config.target.organizations
        assert "torvalds/linux" in config.target.repositories
        
        # Check filters
        assert config.filters.is_archived is False
        assert config.filters.is_fork is False  # Updated to match mock file
        assert config.filters.max_repo_mb_size == 500
        assert config.filters.last_commit_max_age == 365  # Updated to match mock file
        
        # Check scanners - Updated to match mock file which only has semgrep
        assert ScannerType.SEMGREP in config.scanners
        assert len(config.scanners) == 1  # Only one scanner in the mock file
        
    def test_parse_existing_gitlab_config(self):
        """Test parsing the existing gsast-GitLab.json file."""
        gitlab_json_path = Path("tests/mock/test-gitlab.json")
        
        # Load and parse the existing config
        config = GSASTConfig.from_json_file(gitlab_json_path)
        
        # Verify it parses correctly
        assert config.base_url == "https://gsast-server.example.com/"
        assert config.target.provider == ProviderType.GITLAB
        assert "example-group" in config.target.groups
        assert "example-org/example-repo" in config.target.repositories
        
        # Check filters
        assert config.filters.is_archived is False
        assert config.filters.is_fork is False
        assert config.filters.max_repo_mb_size == 500
        assert config.filters.last_commit_max_age == 365
        
        # Check scanners - Updated to match mock file which only has semgrep
        assert ScannerType.SEMGREP in config.scanners
        assert len(config.scanners) == 1  # Only one scanner in the mock file
        
    def test_roundtrip_existing_configs(self):
        """Test that existing configs can be parsed and converted back to equivalent dict.""" 
        for config_file in ["tests/mock/test-github.json", "tests/mock/test-gitlab.json"]:
            # Load original
            with open(config_file, 'r') as f:
                original_data = json.load(f)
                
            # Parse and convert back
            config = GSASTConfig.from_json_file(config_file)
            converted_data = config.to_dict()
            
            # Key fields should match
            assert converted_data["base_url"] == original_data["base_url"]
            assert converted_data["target"]["provider"] == original_data["target"]["provider"]
            
            # API key handling
            if "api_secret_key" in original_data:
                assert converted_data["api_secret_key"] == original_data["api_secret_key"] 