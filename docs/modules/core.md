# gsast-core

Shared library used by all other GSAST modules. Contains data models, configuration, the repository provider abstraction, the scanner plugin interface, and common utilities.

**Package name:** `gsast-core`  
**Python import root:** `gsast_core`  
**Location:** `gsast-core/`

---

## Responsibilities

| Sub-package | Purpose |
|---|---|
| `gsast_core.models` | Pydantic-based data models (`GSASTConfig`, `ScanTargetConfig`, `ScanFilters`, …) |
| `gsast_core.configs` | Environment variable resolution and default values |
| `gsast_core.repolib` | Unified GitHub / GitLab project discovery and repository download |
| `gsast_core.sastlib` | Scanner plugin interface, plugin manager, ruleset downloader, SARIF utilities |
| `gsast_core.utils` | Safe structured logging |

---

## Installation

```bash
pip install -e gsast-core/
```

---

## Configuration

All runtime settings are resolved from environment variables (see `gsast_core.configs`):

| Variable | Required | Description |
|---|---|---|
| `REDIS_URL` | Yes | Full Redis connection URI, e.g. `redis://localhost:6379` |
| `GITLAB_URL` | One of | GitLab instance base URL |
| `GITLAB_API_TOKEN` | One of | GitLab personal access token |
| `GITHUB_API_TOKEN` | One of | GitHub personal access token |

---

## Key interfaces

### `GSASTConfig` — `gsast_core.models.config_models`

The top-level scan configuration. Serialised as JSON and sent from the CLI to the API on every scan request.

```python
from gsast_core.models.config_models import GSASTConfig

config = GSASTConfig.from_json_file("~/.gsast.json")
```

### `ScannerInterface` — `gsast_core.sastlib.scanner_interface`

Base class that every scanner plugin must extend.

```python
from pathlib import Path
from typing import Optional, Dict, List
from gsast_core.sastlib.scanner_interface import ScannerInterface, PluginMetadata, ScannerRequirement

class MyScanner(ScannerInterface):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="my-scanner",
            name="My Scanner",
            version="1.0.0",
            author="Your Name",
            description="What this scanner does",
        )

    def get_requirements(self) -> List[ScannerRequirement]:
        return []

    def validate_requirements(self, **kwargs) -> tuple[bool, Optional[str]]:
        return True, None

    def run_scan(self, project_sources_dir: Path, scan_cwd: Path, **kwargs) -> Optional[Dict[str, Path]]:
        # scanner logic
        pass
```

Register the plugin via `pyproject.toml` entry point:

```toml
[project.entry-points."gsast.scanners"]
my-scanner = "my_scanner_package:MyScanner"
```

### `PluginManager` — `gsast_core.sastlib.plugin_manager`

Discovers all installed scanner plugins via `importlib.metadata` entry points under the `gsast.scanners` group.

### `UnifiedProjectDownloader` — `gsast_core.repolib`

Single entry point for cloning repositories from both GitHub and GitLab.

---

## Redis database indices

| DB | Purpose |
|---|---|
| 0 | Project cache |
| 1 | RQ task queue |
| 2 | Semgrep rule blobs |
| 3 | Scan results and status |

---

## Testing

```bash
cd gsast-core/
pip install -e .
pytest tests/
```
