# Local Development Guide

This guide covers setting up Global SAST Scanner for local development and testing.

## Prerequisites

- **Python 3.9+**
- **Docker** (for Redis)
- **Git**
- **API Tokens**: GitHub and GitLab tokens (see [Installation Guide](installation.md))

## Quick Setup

### Using Quick Start Script

The fastest way to get started:

```bash
./scripts/quick-start.sh --python
```

This automatically:
1. Creates a Python virtual environment at the repo root
2. Installs all modules in editable mode
3. Starts Redis container
4. Configures environment
5. Starts API server and worker

### Manual Setup

#### 1. Clone and Setup Python Environment

```bash
git clone <repository-url>
cd GSAST/
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 2. Install Modules

All four modules are managed as a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) via the root `pyproject.toml`. Install them all in editable mode:

```bash
# Using pip (standard)
pip install -e gsast-core/ -e gsast-api/ -e gsast-worker/ -e gsast-cli/

# Or using uv (faster)
uv sync
```

> Each module can also be installed independently if you only need a subset — see the per-module docs in [docs/modules/](modules/).

#### 3. Install Scanner Binaries

The worker requires Semgrep and TruffleHog:

```bash
pip install semgrep==1.99.0
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin
```

#### 4. Start Redis

Redis is required for job queues and result storage:

```bash
# Using Docker (recommended)
docker run -d --name gsast-redis -p 6379:6379 redis:7-alpine

# Or install locally (macOS)
brew install redis && redis-server
```

#### 5. Configure Environment

```bash
cp env.example .env
```

Edit `.env`:
```bash
# Required
GITHUB_API_TOKEN=ghp_your_github_token_here
GITLAB_API_TOKEN=glpat_your_gitlab_token_here
GITLAB_URL=https://gitlab.com
API_SECRET_KEY=your_secure_random_secret
REDIS_URL=redis://localhost:6379

# Optional for development
FLASK_ENV=development
LOG_LEVEL=DEBUG
```

Generate a secure API secret:
```bash
openssl rand -base64 32
```

#### 6. Start Services

```bash
# Load environment
set -a && source .env && set +a

# Terminal 1 — API server
gsast-api

# Terminal 2 — Worker
gsast-worker

# Terminal 3 — Use the CLI
gsast --help
```

## Development Workflow

### Project Structure

```
GSAST/
├── gsast-core/           # Shared library (models, configs, repolib, sastlib)
│   └── gsast_core/
│       ├── configs/      # Environment variable resolution
│       ├── models/       # Pydantic data models (GSASTConfig, …)
│       ├── repolib/      # GitHub/GitLab repo discovery + download
│       ├── sastlib/      # Plugin interface, manager, SARIF utilities
│       └── utils/        # Logging
│
├── gsast-api/            # Flask API server
│   └── gsast_api/
│       ├── routes/       # Blueprint route handlers
│       ├── services/     # Scan and scanner service logic
│       ├── docs/         # Flasgger YAML spec fragments
│       ├── app.py        # App factory + main()
│       ├── auth.py       # Request authentication
│       └── infra.py      # CLI arg parsing + Redis setup
│
├── gsast-worker/         # RQ worker + scanner plugins
│   └── gsast_worker/
│       ├── plugins/      # semgrep, trufflehog, dependency-confusion
│       ├── tasks.py      # RQ task: clone → scan → store
│       └── worker.py     # RQ Worker setup + main()
│
├── gsast-cli/            # CLI client
│   └── gsast_cli/
│       └── cli_client.py # Click commands
│
├── helm/                 # Kubernetes Helm chart
├── scripts/              # Deployment and utility scripts
└── docs/                 # Documentation
    └── modules/          # Per-module reference docs
```

### Running Tests

```bash
# Run tests for all modules
pytest gsast-core/tests/ gsast-api/tests/ gsast-worker/tests/

# Run with coverage
pytest gsast-core/tests/ --cov=gsast_core --cov-report=html

# Run a specific module's tests
cd gsast-core/ && pytest tests/ -v
cd gsast-api/  && pytest tests/ -v
```

### Code Style and Linting

```bash
pip install black flake8 isort mypy

black gsast-core/ gsast-api/ gsast-worker/ gsast-cli/
isort gsast-core/ gsast-api/ gsast-worker/ gsast-cli/
flake8 gsast-core/ gsast-api/ gsast-worker/ gsast-cli/
```

### Working with the API

```bash
gsast-api
```

Then visit:
- **API Documentation**: http://localhost:5000/apidocs/

Example API calls:
```bash
# Start a scan
curl -X POST http://localhost:5000/scan \
  -H "Content-Type: application/json" \
  -H "API-SECRET-KEY: your-api-secret-key" \
  -d '{
    "config": {
      "target": {
        "provider": "github",
        "organizations": ["your-org"]
      },
      "scanners": ["semgrep", "trufflehog"]
    },
    "rule_files": []
  }'

# Check scan status
curl http://localhost:5000/scan/SCAN-2024-01-01-12-00-00/status \
  -H "API-SECRET-KEY: your-api-secret-key"
```

### Working with the CLI

```bash
cat > ~/.gsast.json << EOF
{
  "api_secret_key": "your-api-secret-key",
  "base_url": "http://localhost:5000",
  "target": {
    "provider": "github",
    "organizations": ["your-org"]
  },
  "scanners": ["semgrep", "trufflehog", "dependency-confusion"]
}
EOF

gsast scan rules/sg_custom/
gsast info SCAN-2024-01-01-12-00-00
gsast results SCAN-2024-01-01-12-00-00
```

See the [CLI reference](modules/cli.md) for all commands and options.

### Adding New Scanners

Scanners are discovered via Python entry points under the `gsast.scanners` group. See the [worker module docs](modules/worker.md#adding-a-custom-scanner-plugin) for a step-by-step guide.

## Debugging

### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
export FLASK_ENV=development
gsast-api
```

### Debug Worker Issues

```bash
export LOG_LEVEL=DEBUG
gsast-worker
```

### Debug Redis Issues

```bash
redis-cli ping
redis-cli monitor
redis-cli keys "*"
redis-cli llen "default"
```

### Debug API Issues

```bash
export FLASK_DEBUG=1
gsast-api
```

## IDE Configuration

### VS Code

Create `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.sortImports.args": ["--profile", "black"]
}
```

Create `.vscode/launch.json` for debugging:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "API Server",
      "type": "python",
      "request": "launch",
      "module": "gsast_api.app",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Worker",
      "type": "python",
      "request": "launch",
      "module": "gsast_worker.worker",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

### PyCharm

1. Set interpreter: `Settings > Project > Python Interpreter > Add > Existing environment > ./venv/bin/python`
2. Set environment file: `Run/Debug Configurations > Environment variables > Load from file > .env`

## Troubleshooting

### Common Development Issues

1. **Import errors after adding a new module:**
   ```bash
   pip install -e gsast-core/ -e gsast-api/ -e gsast-worker/ -e gsast-cli/
   ```

2. **Redis connection errors:**
   ```bash
   redis-cli ping
   docker restart gsast-redis
   ```

3. **Port already in use:**
   ```bash
   lsof -i :5000
   kill -9 <PID>
   # Or use a different port
   export FLASK_RUN_PORT=5001
   ```

4. **SSL certificate errors (corporate networks):**
   ```bash
   export GITHUB_DISABLE_SSL_VERIFY=true
   export PYTHONHTTPSVERIFY=0
   ```

## Contributing

1. **Create a feature branch**: `git checkout -b feature/your-feature`
2. **Write tests**: Add tests for new functionality in the affected module's `tests/` directory
3. **Run tests**: `pytest gsast-core/tests/ gsast-api/tests/`
4. **Check style**: `black . && flake8 .`
5. **Update docs**: Document new features (update the relevant `docs/modules/*.md` file)
6. **Submit PR**: Create pull request with clear description
