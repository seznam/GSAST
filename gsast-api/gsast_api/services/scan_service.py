import json
from collections import defaultdict
from datetime import datetime
from time import sleep
from typing import List, Optional

from redis.client import Redis
from rq import Queue, Worker
from rq.job import Job

import gsast_core.configs.defaults as default_values
from gsast_core.repolib.api import UnifiedRepositoryAPI
from gsast_core.repolib.status_updater import ProjectFetchStatusUpdater
from gsast_core.sastlib.ruleset_downloader import get_rule_key
from gsast_core.utils.safe_logging import log


class TrackedScan:
    def __init__(
        self,
        projects_api: UnifiedRepositoryAPI,
        scans_redis: Redis,
        tasks_queue: Queue,
        rules_redis: Redis,
        rule_files: list,
        scanners: list,
    ):
        self.projects_api: UnifiedRepositoryAPI = projects_api
        self.scans_redis: Redis = scans_redis
        self.tasks_queue: Queue = tasks_queue
        self.rules_redis: Redis = rules_redis
        self.rule_files: list = rule_files
        self.scanners: list = scanners
        self.created_jobs: List[Job] = []
        self.current_jobs: List[Job] = []
        self.scan_id = datetime.now().strftime('SCAN-%Y-%m-%d-%H-%M-%S')
        self._update_scan_status('Scan initiated successfully')

    @staticmethod
    def get_scan_info(scan_id: str, scans_redis: Redis) -> Optional[dict]:
        if not scans_redis.exists(scan_id):
            return None
        return {
            'scan_id': scan_id,
            'message': scans_redis.hget(scan_id, 'message'),
            'jobs': json.loads(scans_redis.hget(scan_id, 'jobs')),
            'status': scans_redis.hget(scan_id, 'status'),
        }

    @staticmethod
    def get_all_scans(scans_redis: Redis) -> List[str]:
        """Return all scan IDs stored in the scans Redis DB."""
        scan_ids: List[str] = []
        for key in scans_redis.keys():
            if ':' in key:
                continue
            if scans_redis.type(key) != 'hash':
                continue
            if scans_redis.hexists(key, 'status'):
                scan_ids.append(key)
        return scan_ids

    def _upload_rules(self) -> List[str]:
        rule_keys = []
        for rule_file in self.rule_files:
            rule_key = get_rule_key(self.scan_id, rule_file['name'])
            self.rules_redis.set(rule_key, rule_file['content'])
            rule_keys.append(rule_key)
        return rule_keys

    def _update_current_jobs(self):
        self.current_jobs = Job.fetch_many(
            [job.id for job in self.created_jobs],
            connection=self.tasks_queue.connection,
        )
        self.current_jobs = [job for job in self.current_jobs if job]

    def _get_current_jobs_status(self) -> defaultdict:
        jobs_by_status = defaultdict(int)
        for job in self.current_jobs:
            jobs_by_status[job.get_status(refresh=False)] += 1
        return jobs_by_status

    def _update_scan_status(self, message_text: str, is_error: bool = False, is_completed: bool = False):
        log_message = f'{message_text} - (scan_id: {self.scan_id})'
        if is_error:
            log.error(log_message)
        else:
            log.info(log_message)

        if is_completed:
            status_text = 'completed'
        elif is_error:
            status_text = 'failed'
        else:
            status_text = 'started'

        self.scans_redis.hset(self.scan_id, mapping={
            'message': message_text,
            'jobs': json.dumps(self._get_current_jobs_status()),
            'status': status_text,
        })

    def _wait_for_workers(self) -> bool:
        self._update_scan_status('Waiting for ready workers to appear...')
        start_time = datetime.now()
        while True:
            workers = Worker.all(queue=self.tasks_queue)
            if workers:
                return True
            if (datetime.now() - start_time).seconds > default_values.SERVER_WAIT_FOR_WORKERS_TIMEOUT:
                return False
            sleep(1)

    def _get_not_finished_jobs_count(self) -> int:
        jobs_by_status = self._get_current_jobs_status()
        return (
            jobs_by_status['queued']
            + jobs_by_status['started']
            + jobs_by_status['deferred']
            + jobs_by_status['scheduled']
        )

    def _wait_for_jobs_to_finish(self):
        total_jobs_count = len(self.created_jobs)
        not_finished_jobs_count = 1
        while not_finished_jobs_count > 0:
            self._update_current_jobs()
            not_finished_jobs_count = self._get_not_finished_jobs_count()
            finished_jobs_count = total_jobs_count - not_finished_jobs_count
            self._update_scan_status(
                f'Waiting for jobs to finish.. Status: {finished_jobs_count}/{total_jobs_count} finished'
            )
            sleep(default_values.SERVER_CHECK_JOBS_STATUS_INTERVAL)

    def run_scan(self):
        self._update_scan_status('Starting scan')

        self._update_scan_status('Uploading provided rules to Redis')
        uploaded_rule_keys = self._upload_rules()

        from gsast_core.sastlib.plugin_manager import plugin_manager
        requirements = plugin_manager.get_plugin_requirements(self.scanners)
        needs_rules = any(
            any(req.name == 'rule_files' and req.required for req in reqs)
            for reqs in requirements.values()
        )

        if not uploaded_rule_keys and needs_rules:
            self._update_scan_status('Error in uploading rules', is_error=True)
            return

        self._update_scan_status('Fetching projects')
        project_fetch_status_updater = ProjectFetchStatusUpdater(
            default_values.SERVER_CHECK_PROJECT_STATUS_INTERVAL,
            self._update_scan_status,
        )
        fetched_projects_count = self.projects_api.fetch_repositories(project_fetch_status_updater)
        self._update_scan_status(f'Fetched {fetched_projects_count} projects')

        if not fetched_projects_count:
            self._update_scan_status('No projects found', is_error=True)
            return

        if not self._wait_for_workers():
            self._update_scan_status(
                f'No workers available - timeout'
                f' ({default_values.SERVER_WAIT_FOR_WORKERS_TIMEOUT} seconds) while waiting for workers',
                is_error=True,
            )
            return

        self._update_scan_status('Processing and enqueuing jobs for projects')
        for project_ssh_url, project_url in zip(
            self.projects_api.get_repositories_ssh_urls(),
            self.projects_api.get_repositories_urls(),
        ):
            new_job = self.tasks_queue.enqueue(
                "gsast_worker.tasks.process_task",
                self.scan_id,
                project_ssh_url,
                uploaded_rule_keys,
                self.scanners,
                project_url=project_url,
                description=self.scan_id,
                job_timeout=default_values.SERVER_JOB_TIMEOUT,
                result_ttl=default_values.SERVER_JOB_RESULT_TTL,
            )
            self.created_jobs.append(new_job)

        self._wait_for_jobs_to_finish()
        self._update_scan_status('Scan successfully finished', is_completed=True)
