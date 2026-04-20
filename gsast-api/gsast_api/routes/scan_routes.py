import shutil
import tempfile
from multiprocessing import Process
from pathlib import Path

from flasgger import swag_from
from flask import Blueprint, g, jsonify, request

from gsast_core.models.config_models import GSASTConfig
from gsast_core.repolib.api import UnifiedRepositoryAPI
from gsast_api.auth import requires_api_key
from gsast_api.services.scan_service import TrackedScan
from gsast_api.services.scanner_service import ScannerService

_DOCS = Path(__file__).parent.parent / 'docs'

scan_bp = Blueprint('scan', __name__)
_scanner_service = ScannerService()


@scan_bp.route('/scan', methods=['POST'])
@swag_from(str(_DOCS / 'scan.yaml'))
@requires_api_key
def start_scan():
    request_data = request.json

    if 'config' not in request_data:
        return jsonify({'error': 'Missing config field'}), 400

    try:
        scan_config = GSASTConfig.from_dict(request_data['config'])
    except (ValueError, KeyError) as e:
        return jsonify({'error': f'Invalid configuration: {e}'}), 400

    rule_files = request_data.get('rule_files', [])
    scanners = scan_config.scanners or _scanner_service.get_default_scanners()

    rules_dir = None
    if rule_files:
        rules_dir = Path(tempfile.mkdtemp())
        try:
            for rule_file in rule_files:
                rule_path = rules_dir / rule_file['name']
                rule_path.parent.mkdir(parents=True, exist_ok=True)
                rule_path.write_text(rule_file['content'])
        except Exception as e:
            shutil.rmtree(rules_dir)
            return jsonify({'error': f'Failed to process rule files: {str(e)}'}), 400

    try:
        is_valid, error_msg = _scanner_service.validate(scanners, rule_files=rule_files, rules_dir=rules_dir)
        if not is_valid:
            if rules_dir:
                shutil.rmtree(rules_dir)
            return jsonify({'error': error_msg}), 400
    except Exception as e:
        if rules_dir:
            shutil.rmtree(rules_dir)
        return jsonify({'error': f'Plugin validation failed: {str(e)}'}), 500

    if rules_dir:
        shutil.rmtree(rules_dir)

    unified_api = UnifiedRepositoryAPI(
        filters=scan_config.filters,
        target=scan_config.target,
        cache_backend=g.redis_projects,
    )

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


@scan_bp.route('/scan/<scan_id>/status', methods=['GET'])
@swag_from(str(_DOCS / 'status.yaml'))
@requires_api_key
def get_scan_status(scan_id: str):
    scan_info = TrackedScan.get_scan_info(scan_id, g.redis_scans)
    if not scan_info:
        return jsonify({'error': 'Scan not found'}), 404
    return jsonify(scan_info), 200
