"""
Tests for the GSAST Plugin System

Tests the plugin manager, plugin discovery, and plugin execution.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, List, Optional

from sastlib.plugin_manager import PluginManager
from sastlib.scanner_interface import (
    ScannerInterface, ScannerRequirement, PluginMetadata
)
from sastlib.sarif_validator import SarifValidator


class MockNativePlugin(ScannerInterface):
    """Mock native plugin for testing"""
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="mock-native-plugin",
            name="Mock Native Plugin",
            version="1.0.0",
            author="Test Author",
            description="Mock plugin for testing"
        )
    
    def get_requirements(self) -> List[ScannerRequirement]:
        return [
            ScannerRequirement(
                name="test_param",
                required=True,
                description="Test parameter"
            )
        ]
    
    def validate_requirements(self, **kwargs) -> tuple[bool, Optional[str]]:
        if "test_param" not in kwargs:
            return False, "test_param is required"
        return True, None
    
    def run_scan(self, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        # Create mock SARIF output
        sarif_file = scan_cwd / "mock_results.sarif"
        
        sarif_content = {
            "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": self.metadata.name,
                            "version": self.metadata.version
                        }
                    },
                    "results": [
                        {
                            "ruleId": "test-rule",
                            "message": {"text": "Test finding"},
                            "level": "warning",
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "test.py"},
                                        "region": {"startLine": 1}
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with open(sarif_file, 'w') as f:
            json.dump(sarif_content, f, indent=2)
        
        return {"test-rule": sarif_file}




class TestPluginManager:
    """Test the plugin manager functionality"""
    
    def test_plugin_manager_initialization(self):
        """Test plugin manager initializes correctly"""
        # Use a fresh plugin manager for testing
        manager = PluginManager()
        
        # Should have initialized without errors
        assert manager is not None
        assert hasattr(manager, '_plugins')
        assert isinstance(manager._plugins, dict)
    
    @patch('importlib.metadata.entry_points')
    def test_plugin_discovery(self, mock_entry_points):
        """Test plugin discovery through entry points"""
        # Mock entry points
        mock_entry_point = Mock()
        mock_entry_point.name = "mock-plugin"
        mock_entry_point.load.return_value = MockNativePlugin
        
        # Python 3.10+ style
        mock_eps = Mock()
        mock_eps.select.return_value = [mock_entry_point]
        mock_entry_points.return_value = mock_eps
        
        # Create plugin manager
        manager = PluginManager()
        
        # Should have discovered the mock plugin
        assert "mock-native-plugin" in manager.list_plugins()
        plugin = manager.get_plugin("mock-native-plugin")
        assert plugin is not None
        assert isinstance(plugin, MockNativePlugin)
    
    def test_plugin_metadata_retrieval(self):
        """Test getting plugin metadata"""
        manager = PluginManager()
        
        # Add mock plugin directly for testing
        mock_plugin = MockNativePlugin()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        # Test metadata retrieval
        metadata = manager.get_plugin_metadata("mock-native-plugin")
        assert metadata is not None
        assert metadata['plugin_id'] == "mock-native-plugin"
        assert metadata['name'] == "Mock Native Plugin"
        assert metadata['version'] == "1.0.0"
    
    def test_plugin_requirements_validation(self):
        """Test plugin requirements validation"""
        manager = PluginManager()
        
        # Add mock plugin
        mock_plugin = MockNativePlugin()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        # Test successful validation
        is_valid, error = manager.validate_plugin_requirements(
            ["mock-native-plugin"], 
            test_param="test_value"
        )
        assert is_valid == True
        assert error is None
        
        # Test failed validation
        is_valid, error = manager.validate_plugin_requirements(
            ["mock-native-plugin"]
        )
        assert is_valid == False
        assert "test_param is required" in error
    
    def test_plugin_requirements_retrieval(self):
        """Test getting plugin requirements"""
        manager = PluginManager()
        
        # Add mock plugin
        mock_plugin = MockNativePlugin()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        # Get requirements
        requirements = manager.get_plugin_requirements(["mock-native-plugin"])
        assert "mock-native-plugin" in requirements
        assert len(requirements["mock-native-plugin"]) == 1
        assert requirements["mock-native-plugin"][0].name == "test_param"
    
    def test_native_plugin_execution(self, tmp_path):
        """Test native plugin execution"""
        manager = PluginManager()
        
        # Add mock plugin
        mock_plugin = MockNativePlugin()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        # Create test directories
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        
        # Run plugin
        results = manager.run_plugin(
            "mock-native-plugin",
            project_dir,
            scan_dir,
            test_param="test_value"
        )
        
        # Should have results
        assert results is not None
        assert "test-rule" in results
        assert results["test-rule"].exists()
    
    def test_unknown_plugin_handling(self):
        """Test handling of unknown plugins"""
        manager = PluginManager()
        
        # Try to get unknown plugin
        plugin = manager.get_plugin("unknown-plugin")
        assert plugin is None
        
        # Try to run unknown plugin
        results = manager.run_plugin("unknown-plugin", Path("/tmp"), Path("/tmp"))
        assert results is None




class TestSarifValidator:
    """Test SARIF validation functionality"""
    
    def test_sarif_validator_initialization(self):
        """Test SARIF validator initializes"""
        validator = SarifValidator()
        assert validator is not None
    
    def test_valid_sarif_validation(self, tmp_path):
        """Test validation of valid SARIF file"""
        validator = SarifValidator()
        
        # Create valid SARIF
        sarif_content = {
            "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Test Scanner",
                            "version": "1.0.0"
                        }
                    },
                    "results": []
                }
            ]
        }
        
        sarif_file = tmp_path / "valid.sarif"
        with open(sarif_file, 'w') as f:
            json.dump(sarif_content, f)
        
        # Validate
        is_valid, error = validator.validate_sarif_file(sarif_file)
        assert is_valid == True
        assert error is None
    
    def test_invalid_sarif_validation(self, tmp_path):
        """Test validation of invalid SARIF file"""
        validator = SarifValidator()
        
        # Create invalid SARIF (missing required fields)
        sarif_content = {
            "version": "2.1.0"
            # Missing schema, runs, etc.
        }
        
        sarif_file = tmp_path / "invalid.sarif"
        with open(sarif_file, 'w') as f:
            json.dump(sarif_content, f)
        
        # Validate
        is_valid, error = validator.validate_sarif_file(sarif_file)
        assert is_valid == False
        assert error is not None
    
    def test_sarif_standardization(self):
        """Test SARIF standardization"""
        validator = SarifValidator()
        
        # Basic SARIF
        sarif_data = {
            "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Test Scanner"
                        }
                    },
                    "results": []
                }
            ]
        }
        
        plugin_metadata = {
            "plugin_id": "test-scanner",
            "version": "1.0.0",
            "author": "Test Author"
        }
        
        # Standardize
        standardized = validator.standardize_sarif_output(sarif_data, plugin_metadata)
        
        # Check standardization
        assert standardized["$schema"] == validator.SARIF_SCHEMA_URL
        assert standardized["version"] == validator.SARIF_VERSION
        
        driver = standardized["runs"][0]["tool"]["driver"]
        assert driver["version"] == "1.0.0"
        assert "gsast" in driver["properties"]
        assert driver["properties"]["gsast"]["pluginId"] == "test-scanner"
    
    def test_empty_sarif_creation(self):
        """Test creation of empty SARIF document"""
        validator = SarifValidator()
        
        plugin_metadata = {
            "plugin_id": "test-scanner",
            "name": "Test Scanner",
            "version": "1.0.0",
            "author": "Test Author"
        }
        
        empty_sarif = validator.create_empty_sarif(plugin_metadata)
        
        # Validate structure
        assert empty_sarif["$schema"] == validator.SARIF_SCHEMA_URL
        assert empty_sarif["version"] == validator.SARIF_VERSION
        assert len(empty_sarif["runs"]) == 1
        assert len(empty_sarif["runs"][0]["results"]) == 0
        
        # Check tool info
        driver = empty_sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "Test Scanner"
        assert driver["version"] == "1.0.0"


class TestPluginIntegration:
    """Integration tests for the complete plugin system"""
    
    def test_end_to_end_native_plugin_execution(self, tmp_path):
        """Test complete native plugin execution flow"""
        # Create test project
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        
        # Create test file
        test_file = project_dir / "test.py"
        test_file.write_text("print('hello world')")
        
        # Create scan directory
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        
        # Create plugin manager with mock plugin
        manager = PluginManager()
        mock_plugin = MockNativePlugin()
        manager._plugins[mock_plugin.metadata.plugin_id] = mock_plugin
        
        # Execute plugin
        results = manager.run_plugin(
            "mock-native-plugin",
            project_dir,
            scan_dir,
            test_param="test_value"
        )
        
        # Verify results
        assert results is not None
        assert "test-rule" in results
        assert results["test-rule"].exists()
        
        # Verify SARIF content
        with open(results["test-rule"], 'r') as f:
            sarif = json.load(f)
        
        assert sarif["version"] == "2.1.0"
        assert len(sarif["runs"]) == 1
        assert sarif["runs"][0]["tool"]["driver"]["name"] == "Mock Native Plugin"
    
    def test_plugin_system_with_multiple_plugins(self, tmp_path):
        """Test plugin system with multiple plugins"""
        manager = PluginManager()
        
        # Add mock plugin
        native_plugin = MockNativePlugin()
        manager._plugins[native_plugin.metadata.plugin_id] = native_plugin
        
        # Test plugin listing
        plugins = manager.list_plugins()
        assert "mock-native-plugin" in plugins
        assert len(plugins) >= 1
        
        # Test getting requirements for plugin
        requirements = manager.get_plugin_requirements([
            "mock-native-plugin"
        ])
        
        assert "mock-native-plugin" in requirements
    
    def test_get_default_plugins_returns_all_plugins(self):
        """Test that get_default_plugins returns all available plugins"""
        manager = PluginManager()
        
        # Add multiple mock plugins
        plugin1 = MockNativePlugin()
        plugin2 = MockNativePlugin()
        plugin2._plugin_id = "mock-plugin-2"  # Override ID for uniqueness
        
        manager._plugins["mock-native-plugin"] = plugin1
        manager._plugins["mock-plugin-2"] = plugin2
        
        # Get default plugins
        default_plugins = manager.get_default_plugins()
        all_plugins = manager.list_plugins()
        
        # Should return all plugins
        assert set(default_plugins) == set(all_plugins)
        assert "mock-native-plugin" in default_plugins
        assert "mock-plugin-2" in default_plugins
    
    def test_plugin_execution_with_sarif_validation(self, tmp_path):
        """Test plugin execution includes SARIF validation"""
        manager = PluginManager()
        
        # Add mock plugin that creates invalid SARIF
        class InvalidSarifPlugin(ScannerInterface):
            @property
            def metadata(self):
                return PluginMetadata(
                    plugin_id="invalid-sarif-plugin",
                    name="Invalid SARIF Plugin",
                    version="1.0.0",
                    author="Test",
                    description="Plugin that creates invalid SARIF"
                )
            
            def get_requirements(self):
                return []
            
            def validate_requirements(self, **kwargs):
                return True, None
            
            def run_scan(self, project_sources_dir, scan_cwd, **kwargs):
                # Create invalid SARIF (missing required fields)
                sarif_file = scan_cwd / "invalid_results.sarif"
                invalid_sarif = {
                    "version": "2.1.0"
                    # Missing schema, runs, etc.
                }
                
                with open(sarif_file, 'w') as f:
                    json.dump(invalid_sarif, f)
                
                return {"invalid-rule": sarif_file}
        
        invalid_plugin = InvalidSarifPlugin()
        manager._plugins[invalid_plugin.metadata.plugin_id] = invalid_plugin
        
        # Create test directories
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        
        # Run plugin - should filter out invalid SARIF
        results = manager.run_plugin("invalid-sarif-plugin", project_dir, scan_dir)
        
        # Should return empty results due to SARIF validation failure
        assert results == {}
    
    def test_plugin_requirements_edge_cases(self):
        """Test plugin requirements validation edge cases"""
        manager = PluginManager()
        
        # Test with non-existent plugin
        is_valid, error = manager.validate_plugin_requirements(["non-existent-plugin"])
        assert is_valid == False
        assert "Unknown plugin" in error
        
        # Test with empty list
        is_valid, error = manager.validate_plugin_requirements([])
        assert is_valid == True
        assert error is None
    
    def test_plugin_error_handling(self, tmp_path):
        """Test plugin error handling during execution"""
        manager = PluginManager()
        
        # Add plugin that raises exception
        class ErrorPlugin(ScannerInterface):
            @property
            def metadata(self):
                return PluginMetadata(
                    plugin_id="error-plugin",
                    name="Error Plugin",
                    version="1.0.0", 
                    author="Test",
                    description="Plugin that raises errors"
                )
            
            def get_requirements(self):
                return []
            
            def validate_requirements(self, **kwargs):
                return True, None
            
            def run_scan(self, project_sources_dir, scan_cwd, **kwargs):
                raise RuntimeError("Intentional test error")
        
        error_plugin = ErrorPlugin()
        manager._plugins[error_plugin.metadata.plugin_id] = error_plugin
        
        # Create test directories
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scan_dir = tmp_path / "scan" 
        scan_dir.mkdir()
        
        # Run plugin - should raise exception
        with pytest.raises(RuntimeError, match="Intentional test error"):
            manager.run_plugin("error-plugin", project_dir, scan_dir)


class TestScannerRequirements:
    """Test scanner requirement system"""
    
    def test_scanner_requirement_creation(self):
        """Test creating scanner requirements"""
        from sastlib.scanner_interface import ScannerRequirement
        
        # Required requirement
        req1 = ScannerRequirement("test_param", required=True, description="Test parameter")
        assert req1.name == "test_param"
        assert req1.required == True
        assert req1.description == "Test parameter"
        
        # Optional requirement
        req2 = ScannerRequirement("optional_param", required=False, description="Optional parameter")
        assert req2.name == "optional_param"
        assert req2.required == False
        assert req2.description == "Optional parameter"
        
        # Default values
        req3 = ScannerRequirement("default_param")
        assert req3.name == "default_param"
        assert req3.required == True  # Default
        assert req3.description == ""  # Default
    
    def test_complex_plugin_requirements(self):
        """Test plugin with complex requirements"""
        class ComplexPlugin(ScannerInterface):
            @property
            def metadata(self):
                return PluginMetadata(
                    plugin_id="complex-plugin",
                    name="Complex Plugin",
                    version="1.0.0",
                    author="Test",
                    description="Plugin with complex requirements"
                )
            
            def get_requirements(self):
                return [
                    ScannerRequirement("required_param", required=True, description="Must be provided"),
                    ScannerRequirement("optional_param", required=False, description="Can be omitted"),
                    ScannerRequirement("config_file", required=True, description="Configuration file path"),
                ]
            
            def validate_requirements(self, **kwargs):
                required_param = kwargs.get('required_param')
                config_file = kwargs.get('config_file')
                
                if not required_param:
                    return False, "required_param is mandatory"
                
                if not config_file:
                    return False, "config_file is mandatory"
                
                if config_file and not Path(config_file).suffix == '.yml':
                    return False, "config_file must be a .yml file"
                
                return True, None
            
            def run_scan(self, project_sources_dir, scan_cwd, **kwargs):
                return {}
        
        plugin = ComplexPlugin()
        manager = PluginManager()
        manager._plugins[plugin.metadata.plugin_id] = plugin
        
        # Test requirements retrieval
        requirements = manager.get_plugin_requirements(["complex-plugin"])
        assert "complex-plugin" in requirements
        assert len(requirements["complex-plugin"]) == 3
        
        # Test successful validation
        is_valid, error = manager.validate_plugin_requirements(
            ["complex-plugin"],
            required_param="value",
            config_file="config.yml",
            optional_param="optional"
        )
        assert is_valid == True
        assert error is None
        
        # Test failed validation - missing required param
        is_valid, error = manager.validate_plugin_requirements(
            ["complex-plugin"],
            config_file="config.yml"
        )
        assert is_valid == False
        assert "required_param is mandatory" in error
        
        # Test failed validation - invalid config file
        is_valid, error = manager.validate_plugin_requirements(
            ["complex-plugin"],
            required_param="value",
            config_file="config.txt"
        )
        assert is_valid == False
        assert "must be a .yml file" in error


# Fixtures for testing
@pytest.fixture
def sample_sarif_content():
    """Sample valid SARIF content for testing"""
    return {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Test Scanner",
                        "version": "1.0.0"
                    }
                },
                "results": [
                    {
                        "ruleId": "test-rule",
                        "message": {"text": "Test issue found"},
                        "level": "warning",
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "src/main.py"},
                                    "region": {"startLine": 42}
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
