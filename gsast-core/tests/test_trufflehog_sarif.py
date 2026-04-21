"""
Test TruffleHog SARIF conversion
"""

import json
import tempfile
from pathlib import Path

from gsast_core.sastlib.results_splitter import convert_trufflehog_to_sarif
from gsast_core.sastlib.sarif_validator import sarif_validator


def test_trufflehog_to_sarif_includes_schema_field():
    """Test that TruffleHog JSON is converted to valid SARIF with $schema field"""
    
    # Create a sample TruffleHog JSON output (line-delimited JSON)
    sample_trufflehog_output = """{"SourceName":"git","DetectorName":"GitLab","DetectorDescription":"GitLab token","Verified":true,"Raw":"glpat-abc123def456","SourceMetadata":{"Data":{"Git":{"commit":"abc123","file":"config.yml","line":10,"repository":"https://gitlab.example.com/project/repo.git"}}}}
{"SourceName":"git","DetectorName":"AWS","DetectorDescription":"AWS Access Key","Verified":false,"Raw":"AKIAIOSFODNN7EXAMPLE","SourceMetadata":{"Data":{"Git":{"commit":"def456","file":"env.js","line":5,"repository":"https://gitlab.example.com/project/repo.git"}}}}"""
    
    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        f.write(sample_trufflehog_output)
        json_path = Path(f.name)
    
    try:
        # Convert to SARIF
        sarif_path = convert_trufflehog_to_sarif(json_path)
        
        # Read the generated SARIF
        with open(sarif_path, 'r', encoding='utf-8') as f:
            sarif_data = json.load(f)
        
        # Test 1: Check $schema field exists
        assert "$schema" in sarif_data, "SARIF document missing required '$schema' field"
        assert sarif_data["$schema"] == "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"
        
        # Test 2: Check version field
        assert "version" in sarif_data
        assert sarif_data["version"] == "2.1.0"
        
        # Test 3: Validate using SARIF validator
        is_valid, error_msg = sarif_validator.validate_sarif_data(sarif_data)
        assert is_valid, f"SARIF validation failed: {error_msg}"
        
        # Test 4: Check results were converted
        assert len(sarif_data["runs"]) == 1
        assert len(sarif_data["runs"][0]["results"]) == 2, "Expected 2 results from sample data"
        
        # Test 5: Check tool information
        tool = sarif_data["runs"][0]["tool"]
        assert tool["driver"]["name"] == "Trufflehog"
        assert "informationUri" in tool["driver"]
        
        # Test 6: Verify result structure
        result = sarif_data["runs"][0]["results"][0]
        assert "ruleId" in result
        assert "message" in result
        assert "text" in result["message"]
        assert "locations" in result
        assert len(result["locations"]) > 0
        
        # Test 7: Verify location structure
        location = result["locations"][0]
        assert "physicalLocation" in location
        assert "artifactLocation" in location["physicalLocation"]
        assert "uri" in location["physicalLocation"]["artifactLocation"]
        
        print("✅ All TruffleHog SARIF conversion tests passed!")
        
    finally:
        # Cleanup
        json_path.unlink()
        if sarif_path.exists():
            sarif_path.unlink()


def test_trufflehog_empty_output():
    """Test that empty TruffleHog output produces valid empty SARIF"""
    
    # Create empty TruffleHog output
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        f.write("")  # Empty file
        json_path = Path(f.name)
    
    try:
        # Convert to SARIF
        sarif_path = convert_trufflehog_to_sarif(json_path)
        
        # Read the generated SARIF
        with open(sarif_path, 'r', encoding='utf-8') as f:
            sarif_data = json.load(f)
        
        # Validate
        is_valid, error_msg = sarif_validator.validate_sarif_data(sarif_data)
        
        # Should still have $schema even with no results
        assert "$schema" in sarif_data, "Empty SARIF should still have $schema field"
        
        # Should have empty results
        assert len(sarif_data["runs"][0]["results"]) == 0
        
        print("Passed: Empty TruffleHog output test")
        
    finally:
        # Cleanup
        json_path.unlink()
        if sarif_path.exists():
            sarif_path.unlink()


if __name__ == "__main__":
    test_trufflehog_to_sarif_includes_schema_field()
    test_trufflehog_empty_output()

