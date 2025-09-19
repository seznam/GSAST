import json
import time
from typing import Dict, Optional, Any, List
from pathlib import Path
from redis.client import Redis
from utils.safe_logging import log


from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.ext import parse as jsonpath_parse_ext
JSONPATH_AVAILABLE = True
def store_scan_results(scans_redis: Redis, scan_id: str, project_url: str, scanner_type: str, 
                      results_paths: Dict[str, Path]) -> bool:
    """
    Store scan results in Redis for later retrieval via API.
    
    Args:
        scans_redis: Redis connection for scans database
        scan_id: Unique identifier for the scan
        project_url: URL of the project being scanned  
        scanner_type: Type of scanner (semgrep, trufflehog, dependency-confusion)
        results_paths: Dictionary mapping rule names to SARIF file paths
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create the key for storing results for this project in this scan
        results_key = f"{scan_id}:results:{project_url}"
        
        # Read and store each SARIF file
        stored_results = {}
        for _, sarif_path in results_paths.items():
            try:
                with open(sarif_path, 'r') as f:
                    sarif_content = json.load(f)
                    stored_results[scanner_type] = sarif_content
                    log.debug(f"Stored {scanner_type} results")
            except Exception as e:
                log.error(f"Failed to read SARIF file {sarif_path}: {e}")
                return False
        
        # Get existing results for this project (if any) and merge
        existing_data = scans_redis.hget(results_key, 'results')
        if existing_data:
            try:
                existing_results = json.loads(existing_data)
                existing_results.update(stored_results)
                stored_results = existing_results
            except json.JSONDecodeError:
                log.warning(f"Could not parse existing results for {results_key}, overwriting")
        
        # Store the results in Redis as a hash
        scans_redis.hset(results_key, mapping={
            'results': json.dumps(stored_results),
            'project_url': project_url,
            'scanner_type': scanner_type,
            'updated_at': str(int(time.time()))
        })
        
        # Add this project to the scan's project list
        projects_key = f"{scan_id}:projects"
        scans_redis.sadd(projects_key, project_url)
        
        log.info(f"Successfully stored {len(results_paths)} {scanner_type} results for {project_url}")
        return True
        
    except Exception as e:
        log.error(f"Failed to store scan results in Redis: {e}", exc_info=True)
        return False


def get_scan_results(scans_redis: Redis, scan_id: str, 
                    project_filter: Optional[str] = None,
                    scanner_filter: Optional[str] = None,
                    jsonpath_query: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve scan results from Redis with optional filtering.
    
    Args:
        scans_redis: Redis connection for scans database
        scan_id: Unique identifier for the scan
        project_filter: Optional project URL/name to filter results
        scanner_filter: Optional scanner type to filter (e.g., 'dependency-confusion', 'semgrep')
        jsonpath_query: Optional JSONPath query to filter SARIF results
        
    Returns:
        Dictionary containing filtered scan results, or None if scan not found
    """
    try:
        # Get list of projects in this scan
        projects_key = f"{scan_id}:projects" 
        project_urls = scans_redis.smembers(projects_key)
        
        if not project_urls:
            return None
        
        # Apply project filter if specified
        if project_filter:
            # Support both full URL and project name matching
            filtered_urls = []
            for url in project_urls:
                if project_filter in url or url.endswith(f"/{project_filter}.git") or url.endswith(f":{project_filter}.git"):
                    filtered_urls.append(url)
            project_urls = filtered_urls
            
            if not project_urls:
                return {
                    'scan_id': scan_id,
                    'projects': {},
                    'message': f'No projects found matching filter: {project_filter}'
                }
            
        all_results = {
            'scan_id': scan_id,
            'projects': {}
        }
        
        # Get results for each project
        for project_url in project_urls:
            results_key = f"{scan_id}:results:{project_url}"
            project_data = scans_redis.hgetall(results_key)
            
            if project_data and 'results' in project_data:
                try:
                    results = json.loads(project_data['results'])
                    
                    # Apply scanner filter if specified
                    if scanner_filter:
                        filtered_results = {}
                        for scanner_type, scanner_data in results.items():
                            if scanner_filter in scanner_type:
                                filtered_results[scanner_type] = scanner_data
                        results = filtered_results
                        
                        if not results:
                            continue  # Skip this project if no matching scanners
                    
                    # Apply JSONPath query if specified
                    if jsonpath_query and JSONPATH_AVAILABLE:
                        results = _apply_jsonpath_filter(results, jsonpath_query)
                        if not results:
                            continue  # Skip if no results match query
                    elif jsonpath_query and not JSONPATH_AVAILABLE:
                        log.error("JSONPath query requested but jsonpath-ng not available")
                        return {
                            'error': 'JSONPath queries require jsonpath-ng library. Install with: pip install jsonpath-ng'
                        }
                    
                    all_results['projects'][project_url] = {
                        'results': results,
                        'updated_at': project_data.get('updated_at')
                    }
                    
                except json.JSONDecodeError:
                    log.warning(f"Could not parse results for {project_url}")
                    
        return all_results
        
    except Exception as e:
        log.error(f"Failed to retrieve scan results from Redis: {e}", exc_info=True)
        return None


def _apply_jsonpath_filter(results: Dict[str, Any], jsonpath_query: str) -> Dict[str, Any]:
    """
    Apply JSONPath filtering to scan results and return raw matches.
    
    Args:
        results: Dictionary of scanner results
        jsonpath_query: JSONPath expression to filter with
        
    Returns:
        Dictionary with raw matched values from JSONPath query
    """
    if not JSONPATH_AVAILABLE:
        return results
        
    filtered_results = {}
    
    try:
        # Parse the JSONPath expression
        jsonpath_expr = jsonpath_parse_ext(jsonpath_query)
        
        for scanner_type, scanner_data in results.items():
            # Apply JSONPath to the full SARIF dict and get raw matches
            matches = [m.value for m in jsonpath_expr.find(scanner_data)]
            if matches:
                filtered_results[scanner_type] = matches
                    
    except Exception as e:
        log.error(f"Failed to apply JSONPath query '{jsonpath_query}': {e}")
        # Return original results on error
        return results
    
    return filtered_results


