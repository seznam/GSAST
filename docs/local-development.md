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
1. Creates Python virtual environment
2. Installs dependencies
3. Starts Redis container
4. Configures environment
5. Starts API server and worker

### Manual Setup

If you prefer step-by-step setup:

#### 1. Clone and Setup Python Environment

```bash
git clone <repository-url>
cd global-sast-scan/gsast
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

#### 2. Start Redis

Redis is required for job queues and result storage:

```bash
# Using Docker (recommended)
docker run -d --name gsast-redis -p 6379:6379 redis:7-alpine

# Or install locally
# macOS
brew install redis
redis-server

# Ubuntu/Debian  
sudo apt install redis-server
sudo systemctl start redis-server
```

#### 3. Configure Environment

Copy the example environment file:
```bash
cp ../env.example .env
```

Edit `.env` with your configuration:
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
# Using OpenSSL
openssl rand -base64 32

# Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 4. Load Environment and Start Services

```bash
# Load environment variables
source .env  # or: export $(cat .env | xargs)

# Start API server (Terminal 1)
python api_server.py

# Start worker (Terminal 2)  
python worker.py

# Use CLI client (Terminal 3)
python cli_client.py --help
```

## Development Workflow

### Project Structure

```
gsast/
├── api_server.py          # Flask API server
├── worker.py              # Background job processor  
├── cli_client.py          # Command-line interface
├── config.py              # Configuration management
├── repolib/              # Repository API integrations
├── sastlib/              # Security scanner integrations  
├── models/               # Data models
└── utils/                # Utility functions
```

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test file
pytest tests/test_unified_repository_api.py -v
```

### Code Style and Linting

```bash
# Install development dependencies
pip install black flake8 isort mypy

# Format code
black .
isort .

# Check style
flake8 .

# Type checking
mypy .
```

### Working with the API

Start the API server and explore:

```bash
python api_server.py
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

# Get results
curl http://localhost:5000/scan/SCAN-2024-01-01-12-00-00/results \
  -H "API-SECRET-KEY: your-api-secret-key"
```

### Working with the CLI

Configure the CLI client:
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
```

Run scans:
```bash
# Start a scan with custom rules
python cli_client.py scan ../rules/sg_custom/

# Check scan status
python cli_client.py info SCAN-2024-01-01-12-00-00

# Get results
python cli_client.py results SCAN-2024-01-01-12-00-00
```

### Adding New Scanners

Scanners are discovered via Python entry points under the `gsast.scanners` group. To add a new scanner:

1. **Create a class** extending `ScannerInterface` from `gsast.sastlib.scanner_interface`:
   ```python
   from pathlib import Path
   from typing import Optional, Dict, List
   from gsast.sastlib.scanner_interface import ScannerInterface, PluginMetadata, ScannerRequirement

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
           # Your scanner logic here
           pass
   ```

2. **Register the entry point** in your package's `pyproject.toml`:
   ```toml
   [project.entry-points."gsast.scanners"]
   my-scanner = "my_scanner_package:MyScanner"
   ```

3. **Install the package** into the same virtual environment as GSAST:
   ```bash
   pip install -e path/to/my-scanner-package
   ```
   Once installed, the plugin is auto-discovered — no changes to GSAST source are required.

4. **Add tests**:
   ```python
   # tests/test_my_scanner.py
   def test_my_scanner():
       pass
   ```

### Debugging

#### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
export FLASK_ENV=development
python api_server.py
```

#### Debug Worker Issues

```bash
# Run worker with more verbose output
export LOG_LEVEL=DEBUG
python worker.py
```

#### Debug Redis Issues

```bash
# Check Redis connection
redis-cli ping

# Monitor Redis commands
redis-cli monitor

# Check job queues
redis-cli keys "*"
redis-cli llen "default"
```

#### Debug API Issues

```bash
# Enable Flask debugging
export FLASK_DEBUG=1
python api_server.py
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
      "program": "api_server.py",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Worker",
      "type": "python", 
      "request": "launch",
      "program": "worker.py",
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

1. **Import errors:**
   ```bash
   # Ensure package is installed in editable mode
   pip install -e .
   
   # Check PYTHONPATH
   export PYTHONPATH=$(pwd):$PYTHONPATH
   ```

2. **Redis connection errors:**
   ```bash
   # Check if Redis is running
   redis-cli ping
   
   # Restart Redis container
   docker restart gsast-redis
   ```

3. **Port already in use:**
   ```bash
   # Find what's using port 5000
   lsof -i :5000
   
   # Kill the process
   kill -9 <PID>
   
   # Or use different port
   export FLASK_RUN_PORT=5001
   ```

4. **SSL certificate errors (corporate networks):**
   ```bash
   # Disable SSL verification for development
   export GITHUB_DISABLE_SSL_VERIFY=true
   export PYTHONHTTPSVERIFY=0
   ```

### Performance Testing

```bash
# Install testing tools
pip install locust pytest-benchmark

# Load test the API
locust -f tests/load_test.py --host=http://localhost:5000

# Benchmark individual functions  
pytest tests/test_performance.py --benchmark-only
```

## Contributing

When contributing to the project:

1. **Create feature branch**: `git checkout -b feature/your-feature`
2. **Write tests**: Add tests for new functionality
3. **Run tests**: `pytest tests/`
4. **Check style**: `black . && flake8 .`
5. **Update docs**: Document new features
6. **Submit PR**: Create pull request with clear description

