# Global SAST Scanner

A distributed security scanning tool for GitLab and GitHub repositories that performs Static Application Security Testing (SAST) using multiple security scanners including Semgrep, TruffleHog, and Dependency Confusion.

## Architecture

GSAST is split into four independent Python packages that share `gsast-core` as a common library:

| Module | Package | Binary | Description |
|---|---|---|---|
| [gsast-core](docs/modules/core.md) | `gsast-core` | — | Shared models, config, repolib, plugin interface |
| [gsast-api](docs/modules/api.md) | `gsast-api` | `gsast-api` | Flask REST API and scan orchestration |
| [gsast-worker](docs/modules/worker.md) | `gsast-worker` | `gsast-worker` | RQ worker that clones repos and runs scanners |
| [gsast-cli](docs/modules/cli.md) | `gsast-cli` | `gsast` | CLI client for submitting scans and fetching results |

```
GSAST/
├── gsast-core/    # Shared library
├── gsast-api/     # API server
├── gsast-worker/  # Background worker + built-in scanner plugins
├── gsast-cli/     # CLI client
├── helm/          # Kubernetes Helm chart
└── scripts/       # Deployment and utility scripts
```

**Data flow:**

```
gsast (CLI) ──POST /scan──► gsast-api ──enqueue──► Redis ──dequeue──► gsast-worker
                                ▲                                          │
                                └──GET /scan/{id}/results ◄── store ──────┘
```

**Infrastructure:** Redis is used for job queues (db=1), Semgrep rule blobs (db=2), scan results (db=3), and project cache (db=0).

## Quick Start

### Super Quick

```bash
# Run the quick start script - it handles everything!
./scripts/quick-start.sh
```

### Standard Deployment

```bash
# 1. Generate environment template
./scripts/deploy-local.sh --generate

# 2. Edit .env file with your API tokens
vim .env

# 3. Deploy to Kubernetes
./scripts/deploy-local.sh --build

# 4. Access the API
./scripts/deploy-local.sh --port-forward
```

Visit http://localhost:5000/apidocs/ to explore the API.

## Installation

For detailed installation instructions, see the [Installation Guide](docs/installation.md).

### Quick Links

- **[gsast-core reference](docs/modules/core.md)** — shared library, plugin interface, configuration
- **[gsast-api reference](docs/modules/api.md)** — REST API endpoints, environment variables
- **[gsast-worker reference](docs/modules/worker.md)** — worker setup, adding custom scanner plugins
- **[gsast-cli reference](docs/modules/cli.md)** — all CLI commands and options
- **[Kubernetes Deployment](docs/kubernetes-deployment.md)** — deploy to Kubernetes clusters
- **[Local Development](docs/local-development.md)** — set up for local development
- **[CLI Client Only](docs/installation.md#3-cli-client-only)** — connect to an existing server

### Requirements

- **Docker** and **kubectl** (for Kubernetes)
- **Python 3.9+** (for local development)
- **API Tokens**: [GitHub](https://github.com/settings/tokens) and [GitLab](https://gitlab.com/-/profile/personal_access_tokens)

```json
{
  "api_secret_key": "your-server-api-key",
  "base_url": "https://your-gsast-server.com",
  "target": {
    "provider": "github",
    "organizations": ["your-org"]
  },
  "scanners": ["semgrep", "trufflehog", "dependency-confusion"]
}
```

## CLI Client Usage

The `gsast` CLI is the primary interface for interacting with the API. Edit `~/.gsast.json` with your settings (created automatically on first run).

#### Start a New Scan

```bash
gsast scan [OPTIONS] [RULE_PATHS...]
```

**Examples:**

```bash
# Scan with custom rules
gsast scan /path/to/rules/

# Scan with additional filters
gsast scan \
  --max-repo-mb-size 100 \
  --is-archived false \
  --last-commit-max-age 30 \
  rules/sg_custom/

# Scan specific GitLab groups
gsast scan \
  --group-ids "security,development" \
  --group-include-subgroups true \
  rules/sg_custom/secrets/
```

**Available Options:**
- `--is-archived BOOL`: Filter out archived repositories
- `--is-fork BOOL`: Filter out forked repositories
- `--is-personal-project BOOL`: Filter out personal projects
- `--max-repo-mb-size INT`: Maximum repository size in MB
- `--ignore-path-regexes TEXT`: Comma-separated path regexes to exclude
- `--must-path-regexes TEXT`: Comma-separated path regexes to require
- `--group-ids TEXT`: GitLab group IDs (comma-separated)
- `--group-with-shared BOOL`: Include projects shared with specified groups
- `--group-include-subgroups BOOL`: Include subgroup projects
- `--last-commit-max-age INT`: Filter repos with last commit older than max-age (days)

#### Check Scan Status

```bash
gsast info {SCAN-ID}
```

#### List All Scans

```bash
gsast scans-status
```

#### Get Scan Results

```bash
gsast results {SCAN-ID}
```

Filter results:

```bash
# Filter by project name/URL
gsast results {SCAN-ID} --project my-repo

# Filter by scanner type
gsast results {SCAN-ID} --scan semgrep

# Use JSONPath for advanced filtering
gsast results {SCAN-ID} --query '$..properties.packageName'

# Combine filters
gsast results {SCAN-ID} \
  --project my-repo \
  --scan dependency-confusion \
  --query '$..results[*].ruleId'
```

#### List Available Scanners

```bash
gsast scanners
```

#### Management Commands

```bash
gsast cleanup-queues    # Clean up scan queues
gsast cleanup-projects  # Clean up project cache
```

### Custom Config Path

```bash
gsast --config /path/to/custom-config.json scan rules/
```

## Configuration File (`~/.gsast.json`)

```json
{
  "api_secret_key": "your-api-secret-key",
  "base_url": "https://your-gsast-server.com",
  "target": {
    "provider": "github|gitlab",
    "organizations": ["org1", "org2"],
    "repositories": ["owner/repo1", "owner/repo2"],
    "groups": ["group1", "group2"]
  },
  "filters": {
    "is_archived": false,
    "is_fork": false,
    "is_personal_project": false,
    "max_repo_mb_size": 500,
    "last_commit_max_age": 365,
    "ignore_path_regexes": ["test", "examples", "mock"],
    "must_path_regexes": []
  },
  "scanners": ["semgrep", "trufflehog", "dependency-confusion"]
}
```

#### Available Scanners

| Scanner | Description |
|---|---|
| `"semgrep"` | Static code analysis using Semgrep rules |
| `"trufflehog"` | Secrets detection in git history |
| `"dependency-confusion"` | Dependency confusion vulnerability detection |

#### Custom TruffleHog Detectors

Place a `trufflehog_config.yaml` file in your config directory. When present it is automatically passed to TruffleHog via `--config`.

See the [TruffleHog custom detectors documentation](https://trufflesecurity.com/blog/trufflehog-custom-detectors) for the YAML format reference.

### How Scans Work

1. **Initiation**: CLI sends a scan request (config + rule files) to `gsast-api`
2. **Project Discovery**: API queries GitHub/GitLab to find repos matching target and filter criteria
3. **Job Creation**: Each repository becomes a separate RQ job in the Redis task queue
4. **Worker Processing**: `gsast-worker` instances pick up jobs and:
   - Clone the repository
   - Run configured scanner plugins (Semgrep, TruffleHog, Dependency Confusion)
   - Store SARIF results in Redis
5. **Result Aggregation**: Results from all repositories are available via the API

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/scan` | Start a new scan |
| `GET` | `/scan/{scan_id}/status` | Get scan status |
| `GET` | `/scan/{scan_id}/results` | Get scan results |
| `GET` | `/scanners` | List available scanner plugins |
| `GET` | `/queue/scans` | List all scan IDs |
| `GET` | `/queue/projects` | List cached projects |
| `DELETE` | `/queue/cleanup` | Clean up scan queues |
| `DELETE` | `/queue/projects` | Clean up project cache |

All endpoints require the `API-SECRET-KEY` request header.

### Example API Calls

```bash
# Start a scan
curl -X POST http://localhost:5000/scan \
  -H "API-SECRET-KEY: your-api-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "api_secret_key": "your-api-secret-key",
      "base_url": "http://localhost:5000",
      "target": {"provider": "github", "organizations": ["my-org"]},
      "scanners": ["semgrep", "trufflehog", "dependency-confusion"]
    },
    "rule_files": []
  }'

# Get scan status
curl http://localhost:5000/scan/SCAN-2024-01-01-12-00-00/status \
  -H "API-SECRET-KEY: your-api-secret-key"

# List available scanners
curl http://localhost:5000/scanners \
  -H "API-SECRET-KEY: your-api-secret-key"
```

### Result Filtering

```
GET /scan/{scan_id}/results?project=my-repo
GET /scan/{scan_id}/results?scan=semgrep
GET /scan/{scan_id}/results?query=$..properties.packageName
```

The `query` param applies a JSONPath expression to each individual SARIF output before merging. For interactive API exploration visit `/apidocs/`.

## Deployment

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `REDIS_URL` | Yes | Redis connection string |
| `GITLAB_API_TOKEN` | One of | GitLab API access token |
| `GITHUB_API_TOKEN` | One of | GitHub API access token |
| `API_SECRET_KEY` | Yes | API authentication key |
| `GITLAB_URL` | No | GitLab instance URL (default: `https://gitlab.com`) |
