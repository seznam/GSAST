import copy
import json
import tempfile
import hashlib

from collections import defaultdict
from typing import Any, Dict, Optional
from pathlib import Path

from utils.safe_logging import log

def write_splitted_results_to_file(sarif_result: Any) -> Path:
    """
    Writes a SARIF object to a temporary JSON file and returns the file path.
    """
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump(sarif_result, f)
        return Path(f.name)

def split_sarif_by_rules(sarif_path: Path) -> Optional[Dict[str, Path]]:
    """
    Splits a single-run SARIF file into multiple SARIF files, one per ruleId.
    Returns a dictionary where each key is the ruleId and each value is the path 
    to the corresponding SARIF file.
    """
    splitted_sarif_results = {}
    with open(sarif_path) as f:
        sarif = json.load(f)
    log.debug(f'Splitting SARIF file: {sarif_path}')

    empty_sarif = copy.deepcopy(sarif)
    empty_sarif['runs'][0]['results'] = []
    sarif_results = defaultdict(lambda: copy.deepcopy(empty_sarif))

    for result in sarif['runs'][0].get('results', []):
        rule_id = result.get('ruleId', 'unknown-rule')
        sarif_results[rule_id]['runs'][0]['results'].append(result)

    for rule_id, sarif_result in sarif_results.items():
        splitted_sarif_results[rule_id] = write_splitted_results_to_file(sarif_result)

    if not splitted_sarif_results:
        log.debug(f'No results found in SARIF file: {sarif_path}')
        return

    return splitted_sarif_results


def convert_trufflehog_to_sarif(json_path: Path) -> Path:
    """
    Reads line-delimited Trufflehog JSON results and converts them into
    a single SARIF file. One SARIF 'rule' is generated per unique detector type
    (keyed by source_name + detector_name + detector_description):
      - The rule's shortDescription contains impact, mitigation, and detector description
      - Each finding becomes a separate 'result' referencing the shared rule

    The final SARIF structure:
      - runs[0].tool.driver.rules[...] -> One rule per unique detector type
      - runs[0].results[...] -> Each result references the ruleId, and has a short 'message.text'.

    Returns:
        Path: A temporary file path containing the generated SARIF JSON.
    """

    impact_text = (
        "Všechny takto uložené secrety musí být revokovány a místo nich je potřeba "
        "vygenerovat nové, které se budou načítat obecně doporučeným a bezpečným "
        "způsobem (sasanka sync atd.). Platí to i pro testovací prostředí, jelikož "
        "nelze zajistit, že tam v budoucnu nepřibudou nějaká nová citlivá data. "
        "Protože se jistě výše nejedná o celkový soupis všech tajemství v rámci "
        "produktu, doporučujeme sjednat nápravu i s tajemstvími, která nebyla během "
        "tohoto testu nalezena."
    )

    mitigation_text = (
        "Kdokoliv, kdo má přístup ke gitlab repositářům, může přihlašovací údaje a "
        "jiná tajemství najít a následně zneužít. Případně o ně může neúmyslně přijít "
        "a zmocnit se jich útočník."
    )

    sarif_template = {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Trufflehog",
                        "informationUri": "https://github.com/trufflesecurity/trufflehog",
                        "rules": []
                    }
                },
                "results": []
            }
        ]
    }

    driver_rules = sarif_template["runs"][0]["tool"]["driver"]["rules"]
    results = []
    seen_detectors = {}  # hash_key -> rule_id
    rule_counter = 0

    with open(json_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                log.warning(f"Skipping invalid JSON line in {json_path}: {line}")
                continue
            
            source_name = data.get("SourceName", "unknown-source")
            detector_name = data.get("DetectorName", "UnknownDetector")
            detector_desc = data.get("DetectorDescription", "")
            raw_secret = data.get("Raw", "")
            verified = data.get("Verified", False)

            git_data = data.get("SourceMetadata", {}).get("Data", {}).get("Git", {})
            commit_id = git_data.get("commit", "")
            file_path = git_data.get("file") or "unknown-file"
            line_number = git_data.get("line", 1)
            repository = git_data.get("repository", "")

            commit_link = ""
            if commit_id and repository:
                repo_url = repository.replace("git@", "https://").replace(".git", "")
                repo_url = repo_url.replace(":", "/").replace("https///", "https://")
                commit_link = f"[{commit_id}]({repo_url}/-/commit/{commit_id})"

            short_msg = f"Hard Coded {detector_name} Secret - {file_path}"

            rule_id_hash = hashlib.sha256()
            rule_id_hash.update(source_name.encode())
            rule_id_hash.update(detector_name.encode())
            rule_id_hash.update(detector_desc.encode())
            hash_key = rule_id_hash.hexdigest()

            if hash_key in seen_detectors:
                rule_id = seen_detectors[hash_key]
            else:
                rule_counter += 1
                rule_id = f"{source_name} {rule_counter}"
                seen_detectors[hash_key] = rule_id

                long_text_parts = []
                long_text_parts.append(f"**Impact:** {impact_text}")
                long_text_parts.append(f"**Mitigation:** {mitigation_text}")
                if detector_desc:
                    long_text_parts.append(f"**Description:** {detector_desc}")
                long_text = "\n\n".join(long_text_parts)

                driver_rules.append({
                    "id": rule_id,
                    "name": f"Trufflehog {detector_name}",
                    "shortDescription": {
                        "text": long_text
                    },
                })

            sarif_result = {
                "ruleId": rule_id,
                "message": {
                    "text": short_msg
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": file_path
                            },
                            "region": {
                                "startLine": line_number
                            },
                            "contextRegion": {
                                "snippet": {
                                    "text": raw_secret
                                }
                            }
                        }
                    }
                ],
                "properties": {
                    "commit": commit_id,
                    "commit_link": commit_link,
                    "repository": repository,
                    "verified": verified,
                    "raw_secret": raw_secret
                }
            }

            results.append(sarif_result)

    sarif_template["runs"][0]["results"] = results

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_sarif:
        json.dump(sarif_template, tmp_sarif, indent=2, ensure_ascii=False)
        sarif_path = Path(tmp_sarif.name)

    return sarif_path

def trufflehog_to_sarif_and_split_by_source(json_path: Optional[Path]) -> Optional[Dict[str, Path]]:
    """
    Converts a line-delimited Trufflehog JSON file into a single SARIF,
    then splits the SARIF results by 'ruleId' (which in our case is the SourceName).
    Returns a dict {source_name: path_to_sarif}.
    """
    if json_path is None:
        return None

    single_sarif_path = convert_trufflehog_to_sarif(json_path)

    splitted = split_sarif_by_rules(single_sarif_path)
    if not splitted:
        log.debug(f'No splitted SARIF generated for file: {json_path}')
        return None

    return splitted
