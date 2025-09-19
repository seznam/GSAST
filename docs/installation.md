# Installation Guide

This guide covers different ways to install and run Global SAST Scanner.

## Prerequisites

Before installing, ensure you have:

- **Python 3.9+** installed
- **Docker** installed and running
- **Git** installed
- **API Tokens**:
  - **GitHub Personal Access Token** with `repo` scope ([Create here](https://github.com/settings/tokens))
  - **GitLab API Token** with `read_api` scope ([GitLab.com](https://gitlab.com/-/profile/personal_access_tokens) or your instance)

## Quick Setup

### Super Quick (2 minutes)

```bash
# Run the quick start script - it handles everything!
./scripts/quick-start.sh
```

The script will:
1. Check requirements (Docker, kubectl, etc.)
2. Create environment configuration
3. Let you choose deployment method (Docker Compose, Kubernetes, or Python)
4. Build and start services
5. Show access information

### Manual Quick Start

```bash
# 1. Copy environment template
cp env.example .env

# 2. Edit .env with your API tokens
vim .env

# 3. Start with existing deployment script
./scripts/deploy-local.sh --build

# 4. Access the API
./scripts/deploy-local.sh --port-forward
```

## Deployment Options

### 1. Kubernetes Deployment (Recommended)

See [Kubernetes Deployment Guide](kubernetes-deployment.md) for detailed instructions.

**Quick version:**
```bash
./scripts/deploy-local.sh --generate  # Create .env template
vim .env                              # Add your tokens
./scripts/deploy-local.sh --build     # Deploy to Kubernetes
./scripts/deploy-local.sh --port-forward  # Access the API
```

### 2. Local Development

See [Local Development Guide](local-development.md) for detailed instructions.

**Quick version:**
```bash
cd gsast/
python -m venv venv
source venv/bin/activate
pip install -e .

# Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine

# Configure environment
export REDIS_URL="redis://localhost:6379"
export GITHUB_API_TOKEN="your_token"
export GITLAB_API_TOKEN="your_token"
export GITLAB_URL="https://gitlab.com"
export API_SECRET_KEY="your_secret"

# Start services
python api_server.py &
python worker.py &
```

### 3. CLI Client Only

If you only need the CLI client to connect to an existing GSAST server:

```bash
cd gsast/
pip install .
python cli_client.py --help
```

Create `~/.gsast.json` configuration:
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

## Environment Configuration

All deployment methods use the same environment variables. Copy `env.example` to `.env` and fill in:

```bash
# Required tokens
GITHUB_API_TOKEN=ghp_your_github_token
GITLAB_API_TOKEN=glpat_your_gitlab_token
GITLAB_URL=https://gitlab.com
API_SECRET_KEY=your_secure_random_key

# Optional configuration
FLASK_ENV=development
LOG_LEVEL=INFO
MAX_REPO_SIZE_MB=500
```

Generate a secure API key:
```bash
openssl rand -base64 32
```

## Verification

After installation, verify everything works:

1. **API Health Check:**
   ```bash
   curl http://localhost:5000/health
   ```

2. **API Documentation:**
   Visit: http://localhost:5000/apidocs/

3. **Run a Test Scan:**
   ```bash
   cd gsast/
   python cli_client.py scan rules/sg_custom/ --max-repo-mb-size 10
   ```

## Troubleshooting

### Common Issues

1. **Port 5000 already in use:**
   ```bash
   # Find what's using the port
   lsof -i :5000
   # Kill the process or use different port
   ```

2. **Redis connection failed:**
   ```bash
   # Start Redis
   docker run -d -p 6379:6379 redis:7-alpine
   # Or install locally
   brew install redis && redis-server
   ```

3. **SSL certificate errors (corporate networks):**
   ```bash
   # Temporarily disable SSL verification
   export GITHUB_DISABLE_SSL_VERIFY=true
   # Or set corporate CA bundle
   export SSL_CERT_FILE=/path/to/corporate-ca.crt
   ```

4. **Permission denied for Docker:**
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   # Then logout and login again
   ```

### Getting Help

- Check logs: `docker-compose logs` or `kubectl logs -l app=gsast`
- Review [troubleshooting guide](troubleshooting.md)
- Open an issue on GitHub

## Next Steps

- [Configure your first scan](configuration.md)
- [Learn about security rules](security-rules.md)
- [Set up continuous scanning](continuous-scanning.md)
