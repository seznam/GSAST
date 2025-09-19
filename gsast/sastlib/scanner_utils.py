import os
import json
import mock
import subprocess
import datetime
import requests
from typing import Dict, Optional
from pathlib import Path

from utils.safe_logging import log


def run_command(command_args, cwd: Path, custom_env=None) -> subprocess.CompletedProcess:
    log.debug(f'Running command: {command_args} in dir: {cwd.absolute()}')
    result = subprocess.run(
        command_args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=dict(os.environ, **custom_env) if custom_env else None,
    )
    log.debug(
        f'Command finished with exit code: {result.returncode} and stderr: {result.stderr}\n'
    )
    return result


def has_findings_sarif(sarif_results_path: Path) -> bool:
    with open(sarif_results_path, 'r') as sarif_results_file:
        sarif_results = json.load(sarif_results_file)
        try:
            if len(sarif_results['runs'][0]['results']) > 0:
                return True
        except KeyError:
            log.error(f'Invalid SARIF file: {sarif_results_path}')
    return False


def has_findings_trufflehog(json_results_path: Path) -> bool:
    with open(json_results_path, 'r') as json_results_file:
        json_result_lines = json_results_file.readlines()

    try:
        json_results = [json.loads(line) for line in json_result_lines]
    except json.JSONDecodeError:
        log.error(f'Invalid JSON file: {json_results_path} with content: {json_result_lines}')
        return False

    if len(json_results):
        return True
    return False


def has_findings(results_path: Path, scan_type: str) -> bool:
    if scan_type == 'SARIF':
        return has_findings_sarif(results_path)
    elif scan_type == 'Trufflehog Scan':
        return has_findings_trufflehog(results_path)
    else:
        log.error(f'Unknown scan type: {scan_type}')
        return False


def update_environment(
    environment,  # Environment object - DefectDojo integration disabled
    rule_id: str,
    results_path: str,
    product_name: str,
    product_type_name: str,
    project_path: str,
    dd_url: str,
    dd_api_key: str,
    test_type_name: str,
):
    environment.url = dd_url
    environment.api_key = dd_api_key
    environment.product_name = product_name
    environment.product_type_name = (product_type_name)
    environment.engagement_name = rule_id
    environment.test_name = project_path
    environment.test_type_name = test_type_name
    environment.file_name = results_path
    environment.active = True
    environment.verified = False
    with mock.patch('sys.stdout', open(os.devnull, 'w')):
        environment.check_environment_reimport_findings()


def upload_results(
    results_paths: Dict[str, Path],
    scan_id: str,
    project_path: str,
    dd_url: str,
    dd_api_key: str,
    scan_type: str,
    do_not_reactivate: bool = False,
) -> bool:
    log.info('Uploading results to DefectDojo')
    upload_status = True
    uploaded_results = 0
    for rule_name, results_path in results_paths.items():
        try:
            if not has_findings(results_path, scan_type):
                log.debug(f'No findings for rule: {rule_name}')
                continue

            # DefectDojo integration disabled for open source release
            log.info(f'DefectDojo upload disabled for open source release')
            # environment = Environment()
            # update_environment(
            #     environment,
            #     rule_name,
            #     str(results_path),
            #     scan_id,
            #     'Research and Development', # default product type that is always present, otherwise same as product_name
            #     str(project_path),
            #     dd_url,
            #     dd_api_key,
            #     scan_type,
            # )

            def mocked_environment_init(self):
                self.__dict__.update(environment.__dict__)

            def mocked_reimport_scan(self, test):
                payload = {
                    'scan_date': datetime.date.today().isoformat(),
                    'scan_type': self.environment.test_type_name,
                    'test': test,
                    'active': self.environment.active,
                    'verified': self.environment.verified,
                    'push_to_jira': self.environment.push_to_jira,
                    'close_old_findings': self.environment.close_old_findings,
                }
                if self.environment.minimum_severity is not None:
                    payload['minimum_severity'] = self.environment.minimum_severity
                if self.environment.group_by is not None:
                    payload['group_by'] = self.environment.group_by
                if self.environment.version is not None:
                    payload['version'] = self.environment.version
                if self.environment.endpoint_id is not None:
                    payload['endpoint_to_add'] = int(self.environment.endpoint_id)
                if self.environment.service is not None:
                    payload['service'] = self.environment.service
                if self.environment.api_scan_configuration_id is not None:
                    payload['api_scan_configuration'] = self.environment.api_scan_configuration_id
                payload['do_not_reactivate'] = do_not_reactivate # force to keep existing findings closed without reactivating them so they will be ignored after triage

                if self.environment.file_name is not None:
                    files = {
                        'file': (
                            self.environment.file_name,
                            open(self.environment.file_name, 'rb'),
                            'application/json',
                            {'Expires': '0'},
                        )
                    }
                    response = requests.post(
                        self.reimport_scan_url,
                        headers=self.headers_without_json,
                        data=payload,
                        files=files,
                        verify=self.ssl_verification,
                    )
                else:
                    response = requests.post(
                        self.reimport_scan_url,
                        headers=self.headers_without_json,
                        data=payload,
                        files={'file': ('', b'')},  # FORCE_MULTIPART
                        verify=self.ssl_verification,
                    )

                response.raise_for_status()
                print()
                print('Scan results imported')

            # DefectDojo API integration disabled for open source release
            log.info(f'DefectDojo API integration disabled for open source release')
            # with mock.patch('dd_import.environment.Environment.__init__', mocked_environment_init), \
            #      mock.patch('dd_import.dd_api.Api.reimport_scan', new=mocked_reimport_scan), \
            #      mock.patch('sys.stdout', open(os.devnull, 'w')):
            #     api = Api()
            #     product_type_id = api.get_product_type()
            #     product_id = api.get_product(product_type_id)
            #     engagement_id = api.get_engagement(product_id)
            #     test_id = api.get_test(engagement_id)
            #     api.reimport_scan(test_id)
            #     api.update_engagement(engagement_id)

            uploaded_results += 1
        except Exception as e:
            log.error(
                f'Error uploading {scan_type} results for scan_id {scan_id}', exc_info=True)
            upload_status = False
            break

    if upload_status:
        if uploaded_results:
            log.info(f'All {uploaded_results} non-empty results were uploaded')
        else:
            log.info('No results were uploaded')
    return upload_status
