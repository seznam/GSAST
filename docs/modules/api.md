# gsast-api

Flask-based HTTP API that manages scan lifecycle: receives scan requests from the CLI, discovers repositories, enqueues per-repo scan jobs into Redis, and serves results.

**Package name:** `gsast-api`  
**Python import root:** `gsast_api`  
**Location:** `gsast-api/`  
**Entry point binary:** `gsast-api`

---

## Responsibilities

- Authenticate incoming requests via `API-SECRET-KEY` header
- Accept scan requests, resolve repository lists (via `gsast-core` repolib), and enqueue RQ jobs
- Serve scan status and SARIF results from Redis
- Expose OpenAPI documentation at `/apidocs/`

---

## Installation

```bash
pip install -e gsast-core/ -e gsast-api/
```

---

## Starting the server

```bash
# From environment variables
export REDIS_URL="redis://localhost:6379"
export GITLAB_API_TOKEN="..."
export API_SECRET_KEY="..."
gsast-api
```

Or with explicit arguments:

```bash
gsast-api \
  --redis-url redis://localhost:6379 \
  --gitlab-url https://gitlab.example.com \
  --gitlab-api-token glpat_xxx \
  --api-secret-key my-secret
```

The server listens on `0.0.0.0:5000`.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `REDIS_URL` | Yes | Redis connection URI |
| `API_SECRET_KEY` | Yes | Authentication key sent in `API-SECRET-KEY` header |
| `GITLAB_URL` | One of | GitLab instance base URL |
| `GITLAB_API_TOKEN` | One of | GitLab personal access token |
| `GITHUB_API_TOKEN` | One of | GitHub personal access token |
| `FLASK_ENV` | No | `development` enables debug mode |

---

## REST endpoints

All endpoints require the `API-SECRET-KEY` request header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/scan` | Start a new scan |
| `GET` | `/scan/{scan_id}/status` | Get scan status |
| `GET` | `/scan/{scan_id}/results` | Get SARIF results |
| `GET` | `/scanners` | List available scanner plugins |
| `GET` | `/queue/scans` | List all scan IDs |
| `GET` | `/queue/projects` | List cached projects |
| `DELETE` | `/queue/cleanup` | Clean up scan queues |
| `DELETE` | `/queue/projects` | Clean up project cache |
| `GET` | `/health` | Health check (no auth required) |

### Result filtering

The `GET /scan/{scan_id}/results` endpoint accepts optional query parameters:

| Parameter | Description |
|---|---|
| `project` | Filter by project name or URL substring |
| `scan` | Filter by scanner type (e.g. `semgrep`, `dependency-confusion`) |
| `query` | JSONPath expression applied per-SARIF output |

### `POST /scan` body

```json
{
  "config": {
    "api_secret_key": "...",
    "base_url": "http://localhost:5000",
    "target": {
      "provider": "github|gitlab",
      "organizations": ["org1"],
      "groups": ["group1"]
    },
    "filters": {
      "is_archived": false,
      "max_repo_mb_size": 500
    },
    "scanners": ["semgrep", "trufflehog", "dependency-confusion"]
  },
  "rule_files": [
    {"name": "my-rule.yaml", "content": "..."}
  ]
}
```

---

## Module structure

```
gsast-api/
├── gsast_api/
│   ├── app.py           # Flask app factory + main()
│   ├── auth.py          # API-SECRET-KEY middleware
│   ├── infra.py         # Argument parsing + Redis setup
│   ├── routes/
│   │   ├── scan_routes.py    # /scan endpoints
│   │   ├── result_routes.py  # /scan/{id}/results, /scan/{id}/status
│   │   └── admin_routes.py   # /queue/*, /scanners, /health
│   ├── services/
│   │   ├── scan_service.py   # Scan orchestration logic
│   │   └── scanner_service.py# Plugin discovery delegation
│   └── docs/            # Flasgger YAML spec fragments
└── tests/
```

---

## Testing

```bash
cd gsast-api/
pip install -e ../gsast-core/ -e .
pytest tests/
```
