import shutil
import tempfile
from typing import List, Optional, Dict
from pathlib import Path

from utils.safe_logging import log


def get_rule_key(scan_id, rule_file):
    return f'{scan_id}:{rule_file}'  # rule_file is a relative path to the rule file


class RawRule:
    def __init__(self, rule_key, rule_content):
        self.scan_id, self.rule_file = rule_key.split(':')
        self.rule_content = rule_content


class RulesetDownloader:
    def __init__(self, rules_redis):
        self.rules_redis = rules_redis
        self.ruleset_dirs_map: Dict[str, Path] = {}

    def __del__(self):
        for scan_id, scan_rules_dir in self.ruleset_dirs_map.items():
            log.debug(f'Removing temporary directory: {scan_rules_dir}')
            shutil.rmtree(scan_rules_dir)

    def _fetch_rule(self, rule_key):
        return self.rules_redis.get(rule_key)

    def _fetch_raw_rules(self, rule_keys):
        return [RawRule(rule_key, self._fetch_rule(rule_key)) for rule_key in rule_keys]

    @staticmethod
    def _save_rule_files(scan_rules_dir: Path, raw_rules: List[RawRule]):
        for raw_rule in raw_rules:
            rule_path = scan_rules_dir / raw_rule.rule_file
            log.debug(f'Saving fetched rule to file: {rule_path}')
            rule_path.parent.mkdir(parents=True, exist_ok=True)
            with open(rule_path, 'wb') as f:
                f.write(raw_rule.rule_content)

    def _download_rules(self, scan_rules_dir, rule_keys):
        raw_rules = self._fetch_raw_rules(rule_keys)
        self._save_rule_files(scan_rules_dir, raw_rules)

    """
    Download rules from Redis and save them to a temporary directory. Rules are cached and directory is reused.
    @param scan_rule_keys: list of rule keys from the same scan id to download
    """

    def get_rules(self, scan_rule_keys) -> Optional[Path]:
        if not scan_rule_keys:
            return None
        scan_id = RawRule(scan_rule_keys[0], None).scan_id
        if scan_id in self.ruleset_dirs_map:
            scan_rules_dir = self.ruleset_dirs_map[scan_id]
            log.info(f'Rules for scan_id: {scan_id} are already downloaded')
        else:
            scan_rules_dir = Path(tempfile.mkdtemp())
            self.ruleset_dirs_map[scan_id] = scan_rules_dir
            log.info(f'Downloading rules for scan_id: {scan_id}')
            try:
                self._download_rules(scan_rules_dir, scan_rule_keys)
            except Exception as e:
                log.error(f'Error while downloading rules for scan_id: {scan_id}: {e}')
                shutil.rmtree(scan_rules_dir)
                return None
        return scan_rules_dir
