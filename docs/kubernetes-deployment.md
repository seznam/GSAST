# Kubernetes Deployment Guide

This guide covers deploying Global SAST Scanner to Kubernetes clusters using the included Helm chart and deployment script.

## Prerequisites

- **kubectl** configured and connected to your cluster
- **Helm v3.x** installed
- **Docker** (for building images)
- **API Tokens**: GitHub and GitLab tokens (see [Installation Guide](installation.md))

## Quick Deployment

### Using the Deployment Script (Recommended)

The repository includes a comprehensive `scripts/deploy-local.sh` script that handles everything:

```bash
# 1. Generate environment template
./scripts/deploy-local.sh --generate

# 2. Edit the .env file with your tokens
vim .env

# 3. Deploy (builds image and installs to Kubernetes)
./scripts/deploy-local.sh --build

# 4. Access the API
./scripts/deploy-local.sh --port-forward
```

That's it! The script handles image building, secret creation, Helm deployment, and provides access instructions.

## Script Options

The deployment script supports many options for different scenarios:

### Basic Usage
```bash
# Deploy with default settings
./scripts/deploy-local.sh

# Build image before deploying  
./scripts/deploy-local.sh --build

# Use existing image from registry
./scripts/deploy-local.sh --image your-registry/gsast:tag

# Deploy to custom namespace
./scripts/deploy-local.sh --namespace my-gsast-namespace
```

### Management Commands
```bash
# Show all available options
./scripts/deploy-local.sh --help

# Port forward to access API locally
./scripts/deploy-local.sh --port-forward

# Clean up and redeploy (if conflicts occur)
./scripts/deploy-local.sh --clean --build

# Force cleanup and redeploy
./scripts/deploy-local.sh --force

# Completely remove deployment and namespace
./scripts/deploy-local.sh --delete
```

### Advanced Options
```bash
# Skip Docker image existence check
./scripts/deploy-local.sh --image custom:tag --skip-image-check

# Custom release name
./scripts/deploy-local.sh --release my-release --namespace my-namespace
```

## Environment Configuration

The script uses a `.env` file for configuration. Generate the template:

```bash
./scripts/deploy-local.sh --generate
```

Then edit `.env` with your values:

```bash
# Required: API authentication
API_SECRET_KEY=your_secure_random_key

# Required: GitHub access  
GITHUB_API_TOKEN=ghp_your_github_token

# Required: GitLab access
GITLAB_URL=https://gitlab.com
GITLAB_API_TOKEN=glpat_your_gitlab_token

# Optional: External Redis (uses internal Redis if not set)
# REDIS_URL=redis://:password@external-redis:6379
```

## Manual Deployment

If you prefer to use Helm directly:

### 1. Prepare the Helm Chart

```bash
# Navigate to chart directory
cd helm/gsast/

# Update dependencies
helm dependency update
```

### 2. Create Namespace and Secrets

```bash
# Create namespace
kubectl create namespace gsast

# Create secret with your credentials
kubectl create secret generic gsast-secret \
  --namespace gsast \
  --from-literal=API_SECRET_KEY="your-secret-key" \
  --from-literal=GITHUB_API_TOKEN="your-github-token" \
  --from-literal=GITLAB_API_TOKEN="your-gitlab-token" \
  --from-literal=GITLAB_URL="https://gitlab.com"
```

### 3. Deploy with Helm

```bash
# Install the chart
helm install gsast . \
  --namespace gsast \
  --set existingSecret=gsast-secret \
  --set worker.image.repositoryPrefix=gsast \
  --set worker.image.tag=latest \
  --set worker.image.pullPolicy=Never
```

### 4. Access the Deployment

```bash
# Port forward to access locally
kubectl port-forward -n gsast service/gsast-api 5000:5000

# Or create an ingress (see values.yaml for configuration)
```

## Cluster-Specific Instructions

### Local Clusters (minikube, kind, Docker Desktop)

The deployment script automatically detects local clusters and:
- Uses `imagePullPolicy: Never` for local images
- Loads built images into the cluster automatically

```bash
# For minikube
./scripts/deploy-local.sh --build
# Script automatically runs: minikube image load gsast:latest

# For kind  
./scripts/deploy-local.sh --build
# Script automatically runs: kind load docker-image gsast:latest

# For Docker Desktop
./scripts/deploy-local.sh --build
# Uses IfNotPresent pull policy
```

### Production Clusters

For production deployments:

```bash
# Build and push to your registry
docker build -t your-registry.com/gsast:v1.0 .
docker push your-registry.com/gsast:v1.0

# Deploy with registry image
./scripts/deploy-local.sh --image your-registry.com/gsast:v1.0
```

## Monitoring and Management

### Check Deployment Status

```bash
# Check pods
kubectl get pods -n gsast-local

# Check services  
kubectl get svc -n gsast-local

# Check deployments
kubectl get deployments -n gsast-local
```

### View Logs

```bash
# API server logs
kubectl logs -n gsast-local -l component=gsast-api -f

# Worker logs
kubectl logs -n gsast-local -l component=gsast-worker -f

# All GSAST logs
kubectl logs -n gsast-local -l app.kubernetes.io/name=gsast -f
```

### Scale Workers

```bash
# Scale workers manually
kubectl scale deployment gsast-worker --replicas=3 -n gsast-local

# Or enable HPA in values.yaml
helm upgrade gsast . \
  --set worker.autoscaling.enabled=true \
  --set worker.autoscaling.minReplicas=2 \
  --set worker.autoscaling.maxReplicas=10
```

## Configuration Options

The Helm chart supports extensive customization through values.yaml:

### Resource Limits
```yaml
api:
  resources:
    limits:
      cpu: 1000m
      memory: 2Gi
    requests:
      cpu: 500m
      memory: 1Gi

worker:
  resources:
    limits:
      cpu: 2000m
      memory: 4Gi
    requests:
      cpu: 1000m
      memory: 2Gi
```

### External Redis
```yaml
redis:
  enabled: false  # Disable internal Redis
useInternalRedis: false

# Configure external Redis via secret
externalRedis:
  existingSecret: "redis-secret"
  existingSecretKey: "redis-url"
```

### Ingress Configuration
```yaml
api:
  ingress:
    enabled: true
    annotations:
      kubernetes.io/ingress.class: nginx
      cert-manager.io/cluster-issuer: letsencrypt-prod
    hosts:
      - host: gsast.your-domain.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: gsast-tls
        hosts:
          - gsast.your-domain.com
```

## Troubleshooting

### Common Issues

1. **Image Pull Errors**
   ```bash
   # Check if image exists in cluster
   kubectl describe pod <pod-name> -n gsast-local
   
   # For local clusters, load the image
   minikube image load gsast:latest
   # or
   kind load docker-image gsast:latest --name <cluster-name>
   ```

2. **Secret Not Found**
   ```bash
   # Verify secret exists
   kubectl get secrets -n gsast-local
   
   # Check secret contents
   kubectl describe secret gsast-local-secret -n gsast-local
   ```

3. **Pod Startup Issues**
   ```bash
   # Check pod events
   kubectl describe pod <pod-name> -n gsast-local
   
   # Check logs for startup errors
   kubectl logs <pod-name> -n gsast-local
   ```

4. **Port Forward Fails**
   ```bash
   # Check if service exists
   kubectl get svc -n gsast-local
   
   # Try different local port
   kubectl port-forward -n gsast-local service/gsast-api 8080:5000
   ```

### Cleanup and Reset

```bash
# Full cleanup
./scripts/deploy-local.sh --delete

# Or manually
helm uninstall gsast -n gsast-local
kubectl delete namespace gsast-local
```

## Next Steps

- [Configure your first scan](configuration.md)
- [Set up monitoring and alerting](monitoring.md)
- [Production deployment best practices](production-deployment.md)
