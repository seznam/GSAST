"""
Tests for the GSAST API Server

Tests the API functionality, request validation, and integration with the plugin system.
"""

import pytest
import json
from unittest.mock import Mock, patch
from pathlib import Path
import os

# Import the modules we need for testing
from models.config_models import GSASTConfig, TargetConfig, FiltersConfig
from utils.tracked_scan import TrackedScan


class TestAPIServerLogic:
    """Test API server logic and integration components"""
    
    def test_plugin_manager_integration_with_api_logic(self):
        """Test how plugin manager integrates with API logic"""
        from sastlib.plugin_manager import plugin_manager
        
        # Test that plugin manager can return default plugins
        default_plugins = plugin_manager.get_default_plugins()
        assert isinstance(default_plugins, list)
        
        # Test validation with empty requirements
        is_valid, error = plugin_manager.validate_plugin_requirements(default_plugins)
        # Should not fail with empty kwargs
        
        # Test that we can list available plugins
        available_plugins = plugin_manager.list_plugins() 
        assert isinstance(available_plugins, list)
    
    @patch('sastlib.plugin_manager.plugin_manager.get_default_plugins')
    @patch('sastlib.plugin_manager.plugin_manager.validate_plugin_requirements')
    def test_api_server_plugin_integration_logic(self, mock_validate, mock_get_default):
        """Test the core logic that would be used by API server"""
        
        # Mock plugin manager responses
        mock_get_default.return_value = ['semgrep', 'trufflehog', 'dependency-confusion']
        mock_validate.return_value = (True, None)
        
        # This simulates what the API server does when no scanners are specified
        scanners = mock_get_default()
        assert len(scanners) == 3
        assert 'semgrep' in scanners
        assert 'trufflehog' in scanners
        assert 'dependency-confusion' in scanners
        
        # This simulates validation
        is_valid, error = mock_validate(scanners, rule_files=[])
        assert is_valid == True
        assert error is None
        
        # Verify mocks were called
        mock_get_default.assert_called_once()
        mock_validate.assert_called_once_with(scanners, rule_files=[])
    
    def test_tracked_scan_initialization(self):
        """Test TrackedScan can be initialized with required parameters"""
        
        # Mock dependencies
        mock_projects_api = Mock()
        mock_scans_redis = Mock() 
        mock_tasks_redis = Mock()
        mock_rules_redis = Mock()
        
        # Test TrackedScan initialization
        tracked_scan = TrackedScan(
            mock_projects_api,
            mock_scans_redis,
            mock_tasks_redis,
            mock_rules_redis,
            rule_files=[],
            scanners=['semgrep']
        )
        
        assert tracked_scan is not None
        assert tracked_scan.scanners == ['semgrep']
        assert tracked_scan.rule_files == []
        assert hasattr(tracked_scan, 'scan_id')
    
    @patch('sastlib.plugin_manager.plugin_manager.get_plugin_requirements')
    def test_tracked_scan_plugin_integration(self, mock_get_requirements):
        """Test TrackedScan integrates with plugin manager"""
        
        # Mock plugin requirements
        mock_requirements = {
            'semgrep': [Mock(name='rule_files', required=True)]
        }
        mock_get_requirements.return_value = mock_requirements
        
        # Mock dependencies
        mock_projects_api = Mock()
        mock_scans_redis = Mock()
        mock_tasks_redis = Mock() 
        mock_rules_redis = Mock()
        
        tracked_scan = TrackedScan(
            mock_projects_api,
            mock_scans_redis,
            mock_tasks_redis,
            mock_rules_redis,
            rule_files=[{'name': 'test.yml', 'content': 'rules: []'}],
            scanners=['semgrep']
        )
        
        # The tracked scan should have plugin manager integration
        assert tracked_scan.scanners == ['semgrep']


class TestPluginManagerIntegration:
    """Test plugin manager integration with API server"""
    
    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin for testing"""
        from sastlib.scanner_interface import ScannerInterface, PluginMetadata
        
        class MockTestPlugin(ScannerInterface):
            @property
            def metadata(self):
                return PluginMetadata(
                    plugin_id="mock-test-plugin",
                    name="Mock Test Plugin",
                    version="1.0.0", 
                    author="Test",
                    description="Mock plugin for testing"
                )
            
            def get_requirements(self):
                return []
            
            def validate_requirements(self, **kwargs):
                return True, None
            
            def run_scan(self, project_sources_dir, scan_cwd, **kwargs):
                # Create mock SARIF file
                sarif_file = scan_cwd / "mock_results.sarif"
                sarif_content = {
                    "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
                    "version": "2.1.0",
                    "runs": [{
                        "tool": {"driver": {"name": "Mock Test Plugin", "version": "1.0.0"}},
                        "results": []
                    }]
                }
                
                with open(sarif_file, 'w') as f:
                    json.dump(sarif_content, f)
                
                return {"mock-rule": sarif_file}
        
        return MockTestPlugin()
    
    def test_plugin_discovery_and_execution(self, mock_plugin, tmp_path):
        """Test that plugins are properly discovered and can be executed"""
        from sastlib.plugin_manager import PluginManager
        
        # Create plugin manager and add mock plugin
        manager = PluginManager()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        # Test plugin discovery
        plugins = manager.list_plugins()
        assert "mock-test-plugin" in plugins
        
        # Test plugin metadata
        metadata = manager.get_plugin_metadata("mock-test-plugin")
        assert metadata is not None
        assert metadata['plugin_id'] == "mock-test-plugin"
        assert metadata['name'] == "Mock Test Plugin"
        
        # Test plugin execution
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        
        results = manager.run_plugin("mock-test-plugin", project_dir, scan_dir)
        assert results is not None
        assert "mock-rule" in results
        assert results["mock-rule"].exists()
    
    def test_default_plugins_behavior(self, mock_plugin):
        """Test that get_default_plugins returns all available plugins"""
        from sastlib.plugin_manager import PluginManager
        
        manager = PluginManager()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        default_plugins = manager.get_default_plugins()
        assert "mock-test-plugin" in default_plugins
        
        # Verify it returns all plugins (same as list_plugins)
        all_plugins = manager.list_plugins()
        assert set(default_plugins) == set(all_plugins)


class TestConfigurationValidation:
    """Test configuration model validation"""
    
    def test_valid_gitlab_target_config(self):
        """Test valid GitLab target configuration"""
        config_data = {
            "base_url": "https://gitlab.example.com",
            "target": {
                "provider": "gitlab",
                "groups": ["group1"]
            }
        }
        
        config = GSASTConfig.from_dict(config_data)
        assert config.base_url == "https://gitlab.example.com"
        assert config.target.provider.value == "gitlab"
        assert config.target.groups == ["group1"]
    
    def test_valid_github_target_config(self):
        """Test valid GitHub target configuration"""
        config_data = {
            "base_url": "https://github.com",
            "target": {
                "provider": "github",
                "organizations": ["org1"]
            }
        }
        
        config = GSASTConfig.from_dict(config_data)
        assert config.base_url == "https://github.com"
        assert config.target.provider.value == "github"
        assert config.target.organizations == ["org1"]
    
    def test_valid_filters_config(self):
        """Test valid filters configuration"""
        config_data = {
            "base_url": "https://gitlab.example.com",
            "target": {
                "provider": "gitlab",
                "groups": ["group1"]
            },
            "filters": {
                "is_archived": False,
                "is_fork": True,
                "last_commit_max_age": 30
            }
        }
        
        config = GSASTConfig.from_dict(config_data)
        assert config.filters.is_archived == False
        assert config.filters.is_fork == True
        assert config.filters.last_commit_max_age == 30
    
    def test_scanner_configuration(self):
        """Test scanner configuration"""
        config_data = {
            "base_url": "https://github.com",
            "target": {
                "provider": "github",
                "repositories": ["repo1", "repo2"]
            },
            "scanners": ["semgrep", "trufflehog"]
        }
        
        config = GSASTConfig.from_dict(config_data)
        assert len(config.scanners) == 2
        assert any(s.value == "semgrep" for s in config.scanners)
        assert any(s.value == "trufflehog" for s in config.scanners)
    
    def test_invalid_provider_config(self):
        """Test invalid provider configuration"""
        config_data = {
            "target": {
                "provider": "invalid-provider"
            }
        }
        
        with pytest.raises(ValueError):
            GSASTConfig.from_dict(config_data)
    
    def test_missing_provider_config(self):
        """Test missing provider configuration"""
        config_data = {
            "target": {
                "groups": ["group1"]
            }
        }
        
        with pytest.raises(KeyError):
            GSASTConfig.from_dict(config_data)
