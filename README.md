# Global SAST Scanner

A distributed security scanning tool for GitLab and GitHub repositories that performs Static Application Security Testing (SAST) using multiple security scanners including Semgrep, Trufflehog, and Confusion Hunter.

## Architecture

The system consists of several key components:

- **CLI Client** (`cli_client.py`): Command-line interface for interacting with the API
- **API Server** (`api_server.py`): Flask-based REST API for managing scans
- **Worker Process** (`worker.py`): Processes individual repository scans
- **Repository API** (`repolib/`): Unified interface for GitHub and GitLab APIs
- **Scanners**: Multiple security scanning engines
- **Redis**: Used for job queues, caching, and result storage

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

- **[Kubernetes Deployment](docs/kubernetes-deployment.md)** - Deploy to Kubernetes clusters
- **[Local Development](docs/local-development.md)** - Set up for local development  
- **[CLI Client Only](docs/installation.md#3-cli-client-only)** - Connect to existing server

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

The CLI client (`cli_client.py`) is the primary interface for interacting with the Global SAST Scanner. Edit `~/.gsast.json` with your specific settings.

#### Start a New Scan

```bash
python3 gsast/cli_client.py scan [OPTIONS] [RULE_PATHS...]
```

**Examples:**

```bash
# Scan with custom rules
python3 gsast/cli_client.py scan /path/to/rules/

# Scan with additional filters
python3 gsast/cli_client.py scan \
  --max-repo-mb-size 100 \
  --is-archived false \
  --last-commit-max-age 30 \
  rules/sg_custom/

# Scan specific GitLab groups
python3 gsast/cli_client.py scan \
  --group-ids "security,development" \
  --group-include-subgroups true \
  rules/sg_custom/secrets/
```

**Available Options:**
- `--is-archived BOOL`: Leave archived repositories unfiltered
- `--is-fork BOOL`: Leave forked repositories unfiltered  
- `--is-personal-project BOOL`: Leave personal projects unfiltered
- `--max-repo-mb-size INT`: Maximum repository size in MB
- `--ignore-path-regexes TEXT`: Comma-separated path regexes to exclude
- `--must-path-regexes TEXT`: Comma-separated path regexes to include
- `--group-ids TEXT`: GitLab group IDs (comma-separated)
- `--group-with-shared BOOL`: Include shared projects in groups
- `--group-include-subgroups BOOL`: Include subgroup projects
- `--last-commit-max-age INT`: Filter repos with last commit older than max-age (in days)

#### Check Scan Status

```bash
python3 gsast/cli_client.py info {SCAN-ID}
```

#### List All Scans

```bash
python3 gsast/cli_client.py scans-status
```

#### Get Scan Results

```bash
python3 gsast/cli_client.py results {SCAN-ID}
```

You can optionally filter results with query parameters equivalent to the API:

```bash
# Filter by project name/URL
python3 gsast/cli_client.py results {SCAN-ID} --project my-repo

# Filter by scanner type
python3 gsast/cli_client.py results {SCAN-ID} --scan semgrep

# Use JSONPath for advanced filtering (quote the expression in the shell)
python3 gsast/cli_client.py results {SCAN-ID} --query '$..properties.packageName'

# Combine filters
python3 gsast/cli_client.py results {SCAN-ID} \
  --project my-repo \
  --scan dependency-confusion \
  --query '$..results[*].ruleId'
```

Notes:
- The CLI handles URL encoding; just wrap JSONPath queries in quotes for your shell.

#### Management Commands

```bash
# Clean up scan queues
python3 gsast/cli_client.py cleanup-queues

# Clean up project cache
python3 gsast/cli_client.py cleanup-projects
```

### Configuration Options

You can specify a custom configuration file:

```bash
python3 gsast/cli_client.py --config {/path/to/custom-config.json} scan {rules/}
```

## Configuration File (`config.json`)

The configuration file defines how the scanner connects to repositories and applies filters. Here's a comprehensive guide to all configuration attributes:

### Basic Structure

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

#### Scanners Configuration (`scanners`)

Available scanner types:

| Scanner | Description |
|---------|-------------|
| `"semgrep"` | Static code analysis using Semgrep rules |
| `"trufflehog"` | Secrets detection in git history |
| `"confusion-hunter"` | Dependency confusion vulnerability detection |


### How Scans Work

- **Initiation**: CLI client sends scan request to API server with configuration and rules
-  **Project Discovery**: Server queries GitHub/GitLab APIs to find repositories matching target and filter criteria
-  **Job Creation**: Each repository becomes a separate job in the Redis queue
-  **Worker Processing**: Worker processes pick up jobs and perform the actual scanning:
   - Clone repository (with or without full git history based on scanner requirements)
   - Run configured scanners (Semgrep, Trufflehog, Confusion Hunter)
   - Store results in Redis
-  **Result Aggregation**: Results from all repositories are available via API server

## API Endpoints

The API server provides REST endpoints for programmatic access:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/scan` | Start a new scan |
| GET | `/scan/{scan_id}/status` | Get scan status |
| GET | `/scan/{scan_id}/results` | Get scan results |
| GET | `/queue/scans` | List all scans |
| GET | `/queue/projects` | List cached projects |
| DELETE | `/queue/cleanup` | Clean up scan queues |
| DELETE | `/queue/projects` | Clean up project cache |

### Result Filtering

The results endpoint supports filtering:

```bash
# Get results for specific project
GET /scan/{scan_id}/results?project=my-repo

# Get results from specific scanner
GET /scan/{scan_id}/results?scan=semgrep

# Use JSONPath queries for advanced filtering
GET /scan/{scan_id}/results?query=$..properties.packageName
```

The query param filters atrributes in the final results by providing a JSON Path. This JSON Path is applied on each separate SARIF (not the final results itself) output from scans. Using this you can display only important parts of json format.

For more detailed info you can check `/apidocs/` to see and try API endpoints.

## Deployment

### Environment Variables

Key environment variables for deployment:

- `REDIS_URL`: Redis connection string
- `GITLAB_API_TOKEN`: GitLab API access token
- `GITHUB_API_TOKEN`: GitHub API access token  
- `API_SECRET_KEY`: API authentication key



