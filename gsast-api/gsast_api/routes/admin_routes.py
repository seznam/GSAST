from pathlib import Path

from flasgger import swag_from
from flask import Blueprint, g, jsonify

from gsast_api.auth import requires_api_key
from gsast_api.services.scan_service import TrackedScan

_DOCS = Path(__file__).parent.parent / 'docs'

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/queue/cleanup', methods=['DELETE'])
@swag_from(str(_DOCS / 'cleanup_queues.yaml'))
@requires_api_key
def cleanup_queues():
    g.redis_scans.flushdb()
    g.redis_tasks.empty()
    g.redis_rules.flushdb()
    return jsonify({'message': 'Scan queues cleaned up successfully'}), 200


@admin_bp.route('/queue/projects', methods=['GET'])
@swag_from(str(_DOCS / 'projects_status.yaml'))
@requires_api_key
def get_projects_cache():
    projects = g.redis_projects.keys()
    return jsonify({'projects': projects}), 200


@admin_bp.route('/queue/scans', methods=['GET'])
@swag_from(str(_DOCS / 'scans_status.yaml'))
@requires_api_key
def get_scans_list():
    try:
        scan_ids = TrackedScan.get_all_scans(g.redis_scans)
        return jsonify({'scans': sorted(scan_ids)}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to list scans: {str(e)}'}), 500


@admin_bp.route('/queue/projects', methods=['DELETE'])
@swag_from(str(_DOCS / 'cleanup_projects.yaml'))
@requires_api_key
def cleanup_projects():
    g.redis_projects.flushdb()
    return jsonify({'message': 'Projects cache cleaned up successfully'}), 200
