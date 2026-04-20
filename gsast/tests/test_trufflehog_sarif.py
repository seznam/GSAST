"""
Test TruffleHog SARIF conversion
"""

import json
import tempfile
from pathlib import Path

from sastlib.results_splitter import convert_trufflehog_to_sarif
from sastlib.sarif_validator import sarif_validator


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
        
        print("Passed: TruffleHog SARIF conversion test")
        
    finally:
        # Cleanup
        json_path.unlink()
        if sarif_path.exists():
            sarif_path.unlink()


def test_trufflehog_rule_deduplication():
    """Test that multiple findings of the same detector type share one rule, 
    and different detector types get distinct rule IDs."""
    
    sample_output = (
        '{"SourceName":"trufflehog - git","DetectorName":"PrivateKey","DetectorDescription":"PK desc","Verified":false,"Raw":"secret1","SourceMetadata":{"Data":{"Git":{"commit":"aaa","file":"file1.pem","line":1,"repository":"https://gitlab.example.com/project/repo.git"}}}}\n'
        '{"SourceName":"trufflehog - git","DetectorName":"PrivateKey","DetectorDescription":"PK desc","Verified":false,"Raw":"secret2","SourceMetadata":{"Data":{"Git":{"commit":"bbb","file":"file2.pem","line":5,"repository":"https://gitlab.example.com/project/repo.git"}}}}\n'
        '{"SourceName":"trufflehog - git","DetectorName":"PrivateKey","DetectorDescription":"PK desc","Verified":false,"Raw":"secret3","SourceMetadata":{"Data":{"Git":{"commit":"ccc","file":"file3.pem","line":10,"repository":"https://gitlab.example.com/project/repo.git"}}}}\n'
        '{"SourceName":"trufflehog - git","DetectorName":"URI","DetectorDescription":"URI desc","Verified":false,"Raw":"http://user:pass@host","SourceMetadata":{"Data":{"Git":{"commit":"ddd","file":"config.js","line":20,"repository":"https://gitlab.example.com/project/repo.git"}}}}\n'
        '{"SourceName":"trufflehog - git","DetectorName":"URI","DetectorDescription":"URI desc","Verified":false,"Raw":"http://admin:admin@host","SourceMetadata":{"Data":{"Git":{"commit":"eee","file":"env.js","line":30,"repository":"https://gitlab.example.com/project/repo.git"}}}}\n'
    )
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        f.write(sample_output)
        json_path = Path(f.name)
    
    try:
        sarif_path = convert_trufflehog_to_sarif(json_path)
        
        with open(sarif_path, 'r', encoding='utf-8') as f:
            sarif_data = json.load(f)
        
        rules = sarif_data["runs"][0]["tool"]["driver"]["rules"]
        results = sarif_data["runs"][0]["results"]
        
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        assert len(rules) == 2, f"Expected 2 rules (PrivateKey + URI), got {len(rules)}"
        
        rule_ids = [r["id"] for r in rules]
        assert len(set(rule_ids)) == 2, f"Rule IDs should be unique, got: {rule_ids}"
        
        pk_rule_id = rules[0]["id"]
        uri_rule_id = rules[1]["id"]
        assert pk_rule_id != uri_rule_id, "PrivateKey and URI must have different rule IDs"
        
        pk_results = [r for r in results if r["ruleId"] == pk_rule_id]
        uri_results = [r for r in results if r["ruleId"] == uri_rule_id]
        assert len(pk_results) == 3, f"Expected 3 PrivateKey results, got {len(pk_results)}"
        assert len(uri_results) == 2, f"Expected 2 URI results, got {len(uri_results)}"
        
        for r in results:
            assert "commit_link" in r["properties"], "Result should have commit_link in properties"
        
        print("Passed: Rule deduplication test")
        
    finally:
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
    test_trufflehog_rule_deduplication()

