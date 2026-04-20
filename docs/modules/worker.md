# gsast-worker

RQ-based background worker that processes repository scan jobs. Clones repositories, runs all configured scanner plugins in sequence, and stores SARIF results in Redis.

**Package name:** `gsast-worker`  
**Python import root:** `gsast_worker`  
**Location:** `gsast-worker/`  
**Entry point binary:** `gsast-worker`

---

## Responsibilities

- Listen on the Redis `tasks` queue for scan jobs enqueued by `gsast-api`
- Clone the target repository (shallow or full history depending on scanner requirements)
- Fetch Semgrep rule blobs from Redis
- Run each enabled scanner plugin via the `PluginManager` from `gsast-core`
- Store per-repository SARIF results back in Redis

---

## Built-in scanner plugins

| Plugin ID | Class | Description |
|---|---|---|
| `semgrep` | `SemgrepPlugin` | Static code analysis via Semgrep rules |
| `trufflehog` | `TrufflehogPlugin` | Secret detection in git history |
| `dependency-confusion` | `DependencyConfusionPlugin` | Dependency confusion vulnerability detection |

All three are registered as entry points under the `gsast.scanners` group in `gsast-worker/pyproject.toml`. Additional third-party plugins can be installed and auto-discovered the same way — see [gsast-core plugin interface](core.md#scannerinterface--gsast_coresastlibscanner_interface).

---

## Installation

```bash
pip install -e gsast-core/ -e gsast-worker/
```

The worker also requires **Semgrep** and **TruffleHog** to be installed on the system (they are included in the Docker image):

```bash
pip install semgrep==1.99.0
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin
```

---

## Starting the worker

```bash
export REDIS_URL="redis://localhost:6379"
export GITLAB_API_TOKEN="..."
gsast-worker
```

Or with explicit arguments:

```bash
gsast-worker \
  --redis-url redis://localhost:6379 \
  --gitlab-url https://gitlab.example.com \
  --gitlab-api-token glpat_xxx
```

The worker starts an RQ `Worker` that listens on the `tasks` queue indefinitely.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `REDIS_URL` | Yes | Redis connection URI |
| `GITLAB_URL` | One of | GitLab instance base URL |
| `GITLAB_API_TOKEN` | One of | GitLab personal access token |
| `GITHUB_API_TOKEN` | One of | GitHub personal access token |

---

## Adding a custom scanner plugin

1. Create a package with a class extending `ScannerInterface` (see [gsast-core docs](core.md#scannerinterface--gsast_coresastlibscanner_interface))
2. Register it in the package's `pyproject.toml`:
   ```toml
   [project.entry-points."gsast.scanners"]
   my-scanner = "my_scanner_package:MyScanner"
   ```
3. Install the package into the same virtual environment as `gsast-worker`:
   ```bash
   pip install -e path/to/my-scanner-package
   ```

The plugin is auto-discovered on next worker startup — no changes to GSAST source are required.

---

## Module structure

```
gsast-worker/
├── gsast_worker/
│   ├── worker.py        # Entry point: RQ Worker setup + main()
│   ├── tasks.py         # RQ task function: clone → scan → store
│   └── plugins/
│       ├── semgrep_plugin.py
│       ├── semgrep_api.py
│       ├── trufflehog_plugin.py
│       ├── trufflehog_api.py
│       ├── dependency_confusion_plugin.py
│       └── dependency_confusion_api.py
└── pyproject.toml
```

---

## Testing

```bash
cd gsast-worker/
pip install -e ../gsast-core/ -e .
pytest tests/
```
