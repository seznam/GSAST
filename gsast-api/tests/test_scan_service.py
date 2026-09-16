from unittest.mock import MagicMock, patch

from gsast_api.services.scan_service import TrackedScan


class TestFailOrphanedScans:
    def test_marks_started_scans_failed(self):
        redis = MagicMock()
        with patch.object(TrackedScan, 'get_all_scans', return_value=['SCAN-1', 'SCAN-2', 'SCAN-3']):
            redis.hget.side_effect = ['started', 'failed', 'started']
            count = TrackedScan.fail_orphaned_scans(redis)

        assert count == 2
        assert redis.hset.call_count == 2
        for hset_call in redis.hset.call_args_list:
            mapping = hset_call.kwargs['mapping']
            assert mapping['status'] == 'failed'
            assert 'interrupted' in mapping['message']

    def test_leaves_completed_and_failed_scans_alone(self):
        redis = MagicMock()
        with patch.object(TrackedScan, 'get_all_scans', return_value=['SCAN-ok']):
            redis.hget.return_value = 'completed'
            assert TrackedScan.fail_orphaned_scans(redis) == 0
        redis.hset.assert_not_called()

    def test_decodes_bytes_status(self):
        redis = MagicMock()
        with patch.object(TrackedScan, 'get_all_scans', return_value=['SCAN-b']):
            redis.hget.return_value = b'started'
            assert TrackedScan.fail_orphaned_scans(redis) == 1
        redis.hset.assert_called_once()


def _bare_scan(projects_api):
    scan = TrackedScan.__new__(TrackedScan)
    scan.scan_id = 'SCAN-test'
    scan.rule_files = []
    scan.scanners = ['config-scanner']
    scan.created_jobs = []
    scan.current_jobs = []
    scan.scans_redis = MagicMock()
    scan.rules_redis = MagicMock()
    scan.tasks_queue = MagicMock()
    scan.projects_api = projects_api
    return scan


class TestRunScanFetchErrors:
    def test_fetch_exception_marks_scan_failed(self):
        api = MagicMock()
        api.fetch_repositories.side_effect = RuntimeError('gitlab 502')
        scan = _bare_scan(api)

        with patch('gsast_core.sastlib.plugin_manager.plugin_manager') as pm:
            pm.get_plugin_requirements.return_value = {}
            scan.run_scan()

        mapping = scan.scans_redis.hset.call_args.kwargs['mapping']
        assert mapping['status'] == 'failed'
        assert 'gitlab 502' in mapping['message']
        scan.tasks_queue.enqueue.assert_not_called()
