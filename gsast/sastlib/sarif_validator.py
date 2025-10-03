"""
SARIF Output Validation and Standardization for GSAST Framework

This module provides utilities to validate and standardize SARIF output from scanner plugins.
We trust scanners to output valid SARIF format and only do basic JSON validation.
"""

import json
from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime, timezone

from utils.safe_logging import log


class SarifValidator:
    """
    Validates and standardizes SARIF output from scanner plugins
    
    We trust scanners to output valid SARIF format and only do basic JSON validation.
    No network calls are made - we rely on scanner plugins to produce valid SARIF.
    """
    
    SARIF_SCHEMA_URL = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"
    SARIF_VERSION = "2.1.0"
    
    def __init__(self):
        pass
    
    def validate_sarif_file(self, sarif_file_path: Path) -> tuple[bool, Optional[str]]:
        """
        Validate a SARIF file
        
        Args:
            sarif_file_path: Path to SARIF file to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not sarif_file_path.exists():
            return False, f"SARIF file does not exist: {sarif_file_path}"
        
        try:
            with open(sarif_file_path, 'r', encoding='utf-8') as f:
                sarif_data = json.load(f)
            
            return self.validate_sarif_data(sarif_data)
            
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON in SARIF file: {e}"
        except Exception as e:
            return False, f"Error reading SARIF file: {e}"
    
    def validate_sarif_data(self, sarif_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate SARIF data structure
        
        Args:
            sarif_data: SARIF data as dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Basic structure validation only
        basic_valid, basic_error = self._validate_basic_structure(sarif_data)
        if not basic_valid:
            return False, basic_error
        
        # GSAST-specific validation
        gsast_valid, gsast_error = self._validate_gsast_requirements(sarif_data)
        if not gsast_valid:
            return False, gsast_error
        
        return True, None
    
    def _validate_basic_structure(self, sarif_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate basic SARIF structure requirements"""
        
        # Check required top-level fields
        if not isinstance(sarif_data, dict):
            return False, "SARIF data must be a JSON object"
        
        if "$schema" not in sarif_data:
            return False, "SARIF document missing required '$schema' field"
        
        if "version" not in sarif_data:
            return False, "SARIF document missing required 'version' field"
        
        if sarif_data["version"] != self.SARIF_VERSION:
            return False, f"SARIF version must be '{self.SARIF_VERSION}', got '{sarif_data.get('version')}'"
        
        if "runs" not in sarif_data:
            return False, "SARIF document missing required 'runs' field"
        
        if not isinstance(sarif_data["runs"], list):
            return False, "SARIF 'runs' field must be an array"
        
        if len(sarif_data["runs"]) == 0:
            return False, "SARIF document must contain at least one run"
        
        # Validate each run
        for i, run in enumerate(sarif_data["runs"]):
            run_valid, run_error = self._validate_run(run, i)
            if not run_valid:
                return False, f"Run {i}: {run_error}"
        
        return True, None
    
    def _validate_run(self, run: Dict[str, Any], run_index: int) -> tuple[bool, Optional[str]]:
        """Validate a SARIF run object"""
        
        if not isinstance(run, dict):
            return False, "Run must be an object"
        
        if "tool" not in run:
            return False, "Run missing required 'tool' field"
        
        tool_valid, tool_error = self._validate_tool(run["tool"])
        if not tool_valid:
            return False, f"Tool validation failed: {tool_error}"
        
        if "results" not in run:
            return False, "Run missing required 'results' field"
        
        if not isinstance(run["results"], list):
            return False, "Run 'results' field must be an array"
        
        # Validate each result
        for i, result in enumerate(run["results"]):
            result_valid, result_error = self._validate_result(result, i)
            if not result_valid:
                return False, f"Result {i}: {result_error}"
        
        return True, None
    
    def _validate_tool(self, tool: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate a SARIF tool object"""
        
        if not isinstance(tool, dict):
            return False, "Tool must be an object"
        
        if "driver" not in tool:
            return False, "Tool missing required 'driver' field"
        
        driver = tool["driver"]
        if not isinstance(driver, dict):
            return False, "Tool driver must be an object"
        
        if "name" not in driver:
            return False, "Tool driver missing required 'name' field"
        
        if not isinstance(driver["name"], str) or not driver["name"].strip():
            return False, "Tool driver name must be a non-empty string"
        
        return True, None
    
    def _validate_result(self, result: Dict[str, Any], result_index: int) -> tuple[bool, Optional[str]]:
        """Validate a SARIF result object"""
        
        if not isinstance(result, dict):
            return False, "Result must be an object"
        
        if "message" not in result:
            return False, "Result missing required 'message' field"
        
        message = result["message"]
        if not isinstance(message, dict):
            return False, "Result message must be an object"
        
        if "text" not in message:
            return False, "Result message missing required 'text' field"
        
        if not isinstance(message["text"], str) or not message["text"].strip():
            return False, "Result message text must be a non-empty string"
        
        if "locations" not in result:
            return False, "Result missing required 'locations' field"
        
        if not isinstance(result["locations"], list):
            return False, "Result locations must be an array"
        
        if len(result["locations"]) == 0:
            return False, "Result must have at least one location"
        
        # Validate each location
        for i, location in enumerate(result["locations"]):
            location_valid, location_error = self._validate_location(location, i)
            if not location_valid:
                return False, f"Location {i}: {location_error}"
        
        return True, None
    
    def _validate_location(self, location: Dict[str, Any], location_index: int) -> tuple[bool, Optional[str]]:
        """Validate a SARIF location object"""
        
        if not isinstance(location, dict):
            return False, "Location must be an object"
        
        if "physicalLocation" not in location:
            return False, "Location missing required 'physicalLocation' field"
        
        physical_location = location["physicalLocation"]
        if not isinstance(physical_location, dict):
            return False, "Physical location must be an object"
        
        if "artifactLocation" not in physical_location:
            return False, "Physical location missing required 'artifactLocation' field"
        
        artifact_location = physical_location["artifactLocation"]
        if not isinstance(artifact_location, dict):
            return False, "Artifact location must be an object"
        
        if "uri" not in artifact_location:
            return False, "Artifact location missing required 'uri' field"
        
        if not isinstance(artifact_location["uri"], str) or not artifact_location["uri"].strip():
            return False, "Artifact location uri must be a non-empty string"
        
        return True, None
    
    def _validate_gsast_requirements(self, sarif_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate GSAST-specific requirements"""
        
        # GSAST doesn't have specific requirements beyond basic SARIF structure
        # We trust scanners to produce valid SARIF format
        return True, None
    
    def standardize_sarif_output(self, sarif_data: Dict[str, Any], plugin_metadata: Dict[str, str]) -> Dict[str, Any]:
        """
        Standardize SARIF output with GSAST metadata
        
        Args:
            sarif_data: Original SARIF data
            plugin_metadata: Plugin metadata to add
            
        Returns:
            Standardized SARIF data
        """
        # Create a copy to avoid modifying original
        standardized = json.loads(json.dumps(sarif_data))
        
        # Ensure each run has GSAST metadata in tool properties
        for run in standardized.get("runs", []):
            tool = run.get("tool", {})
            driver = tool.get("driver", {})
            
            # Update tool metadata if provided
            if "name" in plugin_metadata:
                driver["name"] = plugin_metadata["name"]
            if "version" in plugin_metadata:
                driver["version"] = plugin_metadata["version"]
            if "homepage" in plugin_metadata:
                driver["informationUri"] = plugin_metadata["homepage"]
            
            # Add GSAST metadata to tool properties
            if "properties" not in driver:
                driver["properties"] = {}
            
            driver["properties"]["gsast"] = {
                "pluginId": plugin_metadata.get("plugin_id", "unknown"),
                "pluginAuthor": plugin_metadata.get("author", "unknown"),
                "scanTimestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                "gsastVersion": "0.1.0"
            }
        
        return standardized
    
    def create_empty_sarif(self, plugin_metadata: Dict[str, str]) -> Dict[str, Any]:
        """
        Create an empty SARIF document for plugins with no results
        
        Args:
            plugin_metadata: Plugin metadata
            
        Returns:
            Empty but valid SARIF document
        """
        return {
            "$schema": self.SARIF_SCHEMA_URL,
            "version": self.SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": plugin_metadata.get("name", "Unknown Scanner"),
                            "version": plugin_metadata.get("version", "1.0.0"),
                            "informationUri": plugin_metadata.get("homepage", ""),
                            "properties": {
                                "gsast": {
                                    "pluginId": plugin_metadata.get("plugin_id", "unknown"),
                                    "pluginAuthor": plugin_metadata.get("author", "unknown"),
                                    "scanTimestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                                    "gsastVersion": "0.1.0"
                                }
                            }
                        }
                    },
                    "results": []
                }
            ]
        }


# Global SARIF validator instance
sarif_validator = SarifValidator()