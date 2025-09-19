from functools import wraps
from hmac import compare_digest
import os

from flask import Flask, request, jsonify, g
from multiprocessing import Process
from redis.client import Redis
from requests_cache import RedisCache
from rq import Queue
from flasgger import Swagger, swag_from

from utils import infra_cli
from repolib.api import UnifiedRepositoryAPI
from models.config_models import GSASTConfig
from utils.tracked_scan import TrackedScan
from sastlib.results_storage import get_scan_results


REDIS_SCANS: Redis = None
REDIS_TASKS: Queue = None
REDIS_RULES: Redis = None
REDIS_PROJECTS: Redis = None

def init_app():
    global REDIS_SCANS, REDIS_TASKS, REDIS_RULES, REDIS_PROJECTS, GITLAB_URL, GITLAB_API_TOKEN, GITHUB_API_TOKEN, API_SECRET_KEY
    cli_args = infra_cli.parse_args('Global SAST scan API. Run distributed scan on GitHub and GitLab projects')
    GITLAB_URL, GITLAB_API_TOKEN = cli_args.gitlab_url, cli_args.gitlab_api_token
    # Add GitHub token support (should be added to infra_cli.py)
    GITHUB_API_TOKEN = getattr(cli_args, 'github_api_token', None) or os.getenv('GITHUB_API_TOKEN')
    REDIS_SCANS, _, REDIS_TASKS, REDIS_RULES = infra_cli.setup_redis_queues(cli_args.redis_url)
    REDIS_PROJECTS = infra_cli.setup_redis_cache(cli_args.redis_url)
    API_SECRET_KEY = cli_args.api_secret_key
    

app = Flask(__name__)
swagger = Swagger(app)

init_app()


def requires_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'API-SECRET-KEY' not in request.headers or not compare_digest(request.headers['API-SECRET-KEY'],
                                                                         g.API_SECRET_KEY):
            return jsonify({'error': 'Invalid API-SECRET-KEY'}), 403
        return f(*args, **kwargs)

    return decorated_function


@app.before_request
def before_request():
    g.redis_scans = REDIS_SCANS
    g.redis_tasks = REDIS_TASKS
    g.redis_rules = REDIS_RULES
    g.redis_projects = REDIS_PROJECTS
    g.gitlab_url = GITLAB_URL
    g.GITLAB_API_TOKEN = GITLAB_API_TOKEN
    g.GITHUB_API_TOKEN = GITHUB_API_TOKEN
    g.API_SECRET_KEY = API_SECRET_KEY


# def start_background_scan(tracked_scan: TrackedScan):
#     tracked_scan.run_scan()


@app.route('/scan', methods=['POST'])
@swag_from('docs/scan.yaml')
@requires_api_key
def start_scan():
    request_data = request.json
    
    if 'config' in request_data:
        try:
            scan_config = GSASTConfig.from_dict(request_data['config'])
        except (ValueError, KeyError) as e:
            return jsonify({'error': f'Invalid configuration: {e}'}), 400
        
        rule_files = request_data.get('rule_files', [])
        
    else:
        return jsonify({'error': 'Missing config field'}), 400
    
    # Validate rule files if semgrep is enabled
    if scan_config.scanners and 'semgrep' in scan_config.scanners:
        if not rule_files or not isinstance(rule_files, list):
            return jsonify({'error': 'Rule files are required'}), 400

        for rule_file in rule_files:
            if 'name' not in rule_file or 'content' not in rule_file:
                return jsonify({'error': 'Rule file must contain "name" and "content" fields'}), 400
            if not rule_file['name'].endswith(('.yaml', '.yml', '.json')):
                return jsonify({'error': f'Rule file {rule_file["name"]} is not in .yaml or .json format'}), 400

    # initialize unified API
    cache_backend = RedisCache(connection=g.redis_projects)
    unified_api = UnifiedRepositoryAPI(filters=scan_config.filters, 
                                       target=scan_config.target,
                                       cache_backend=cache_backend)

    # Extract scanner settings
    scanners = [s.value for s in (scan_config.scanners or ['semgrep'])]

    tracked_scan = TrackedScan(
        unified_api, 
        g.redis_scans, 
        g.redis_tasks, 
        g.redis_rules, 
        rule_files, 
        scanners, 
    )

    scan_process = Process(target=tracked_scan.run_scan)
    scan_process.start()

    return jsonify({'scan_id': tracked_scan.scan_id}), 200


@app.route('/scan/<scan_id>/status', methods=['GET'])
@swag_from('docs/status.yaml')
@requires_api_key
def get_scan_status(scan_id: str):
    scan_info = TrackedScan.get_scan_info(scan_id, g.redis_scans)
    if not scan_info:
        return jsonify({'error': 'Scan not found'}), 404

    return jsonify(scan_info), 200


@app.route('/scan/<scan_id>/results', methods=['GET'])
@swag_from('docs/results.yaml')
@requires_api_key
def get_scan_results_endpoint(scan_id: str):
    """
    Get scan results for a specific scan ID with optional filtering.
    
    Query Parameters:
        project: Filter results to specific project name/URL
        scan: Filter results to specific scanner type (e.g., 'dependency-confusion', 'semgrep')  
        query: JSONPath query to extract specific data from SARIF results (returns raw matched values)
    
    Examples:
        /scan/123/results - Get all results
        /scan/123/results?project=deepkeep - Get results for deepkeep project only
        /scan/123/results?scan=dependency-confusion - Get only dependency confusion results
        /scan/123/results?query=$..rules[?(@.properties.precision=="high")] - Get high precision rules
        /scan/123/results?query=$..results[?(@.level=="warning")] - Get warning-level findings
        /scan/123/results?query=$..results[*].ruleId - Get all rule IDs
        /scan/123/results?query=$..properties.tags - Get all rule tags
    """
    try:
        # Extract query parameters
        project_filter = request.args.get('project')
        scanner_filter = request.args.get('scan') 
        jsonpath_query = request.args.get('query')
        
        # Get filtered results
        scan_results = get_scan_results(
            g.redis_scans, 
            scan_id, 
            project_filter=project_filter,
            scanner_filter=scanner_filter, 
            jsonpath_query=jsonpath_query
        )
        
        if not scan_results:
            return jsonify({'error': 'Scan results not found'}), 404

        # Add filter info to response if filters were applied
        if project_filter or scanner_filter or jsonpath_query:
            scan_results['filters_applied'] = {
                'project': project_filter,
                'scanner': scanner_filter, 
                'jsonpath_query': jsonpath_query
            }

        return jsonify(scan_results), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve scan results: {str(e)}'}), 500


@app.route('/queue/cleanup', methods=['DELETE'])
@swag_from('docs/cleanup_queues.yaml')
@requires_api_key
def cleanup_queues():
    g.redis_scans.flushdb()
    g.redis_tasks.empty()
    g.redis_rules.flushdb()
    return jsonify({'message': 'Scan queues cleaned up successfully'}), 200


@app.route("/queue/projects", methods=['GET'])
@swag_from('docs/projects_status.yaml')
@requires_api_key
def get_projects_cache():
    # list all projects in redis cache
    projects = g.redis_projects.keys()
    return jsonify({'projects': projects}), 200

@app.route("/queue/scans", methods=['GET'])
@swag_from('docs/scans_status.yaml')
@requires_api_key
def get_scans_list():
    # List all scan IDs stored in scans Redis
    try:
        scan_ids = TrackedScan.get_all_scans(g.redis_scans)

        return jsonify({'scans': sorted(scan_ids)}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to list scans: {str(e)}'}), 500


@app.route('/queue/projects', methods=['DELETE'])
@swag_from('docs/cleanup_projects.yaml')
@requires_api_key
def cleanup_projects():
    g.redis_projects.flushdb()
    return jsonify({'message': 'Projects cache cleaned up successfully'}), 200


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
