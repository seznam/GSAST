from pathlib import Path

from flasgger import swag_from
from flask import Blueprint, current_app, g, jsonify, request

from gsast_core.sastlib.results_storage import get_scan_results
from gsast_api.auth import requires_api_key

_DOCS = Path(__file__).parent.parent / 'docs'

result_bp = Blueprint('result', __name__)


@result_bp.route('/scan/<scan_id>/results', methods=['GET'])
@swag_from(str(_DOCS / 'results.yaml'))
@requires_api_key
def get_scan_results_endpoint(scan_id: str):
    """
    Get scan results for a specific scan ID with optional filtering.

    Query Parameters:
        project: Filter results to specific project name/URL
        scan: Filter results to specific scanner type
        query: JSONPath expression to extract data from SARIF results
    """
    try:
        project_filter = request.args.get('project')
        scanner_filter = request.args.get('scan')
        jsonpath_query = request.args.get('query')

        scan_results = get_scan_results(
            g.redis_scans,
            scan_id,
            project_filter=project_filter,
            scanner_filter=scanner_filter,
            jsonpath_query=jsonpath_query,
        )

        if not scan_results:
            return jsonify({'error': 'Scan results not found'}), 404

        if project_filter or scanner_filter or jsonpath_query:
            scan_results['filters_applied'] = {
                'project': project_filter,
                'scanner': scanner_filter,
                'jsonpath_query': jsonpath_query,
            }

        return jsonify(scan_results), 200

    except Exception as e:
        return jsonify({'error': f'Failed to retrieve scan results: {str(e)}'}), 500


@result_bp.route('/scanners', methods=['GET'])
@swag_from(str(_DOCS / 'scanners.yaml'))
@requires_api_key
def get_available_scanners():
    try:
        scanner_service = current_app.config['SCANNER_SERVICE']
        scanners = scanner_service.list_scanners()
        return jsonify({'scanners': scanners, 'count': len(scanners)}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve scanners: {str(e)}'}), 500
