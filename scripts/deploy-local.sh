#!/bin/bash

# GSAST Local Deployment Script
# This script deploys GSAST locally using secrets from a .env file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CHART_DIR="$PROJECT_ROOT/helm/gsast"
ENV_FILE="$PROJECT_ROOT/.env"
NAMESPACE="gsast-local"
RELEASE_NAME="gsast-local"
DOCKER_IMAGE="gsast:latest"
BUILD_IMAGE=false
SKIP_IMAGE_CHECK=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show help
show_help() {
    cat << EOF
GSAST Local Deployment Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --generate    Generate an empty .env template file
    --help        Show this help message
    --port-forward, --pf  Port-forward to the GSAST API (port 5000)
    --namespace   Specify namespace (default: gsast-local)
    --release     Specify release name (default: gsast-local)
    --clean       Clean up existing deployment before installing
    --force       Force cleanup and redeploy (use if deployment conflicts occur)
    --build       Build Docker image before deployment
    --image       Specify Docker image (default: gsast:latest)
    --skip-image-check  Skip Docker image existence check
    --delete      Uninstall Helm release and delete entire namespace

EXAMPLES:
    $0                           # Deploy using .env file (requires image to exist)
    $0 --generate                # Generate .env template
    $0 --build                   # Build image and deploy
    $0 --port-forward            # Port-forward to API after deployment
    $0 --pf                      # Short alias for port-forward
    $0 --image my-registry/gsast:v1.0  # Use specific image
    $0 --namespace my-gsast      # Deploy to custom namespace
    $0 --clean                   # Clean up and redeploy
    $0 --force                   # Force cleanup if there are conflicts

REQUIREMENTS:
    - kubectl configured and connected to cluster
    - helm v3.x installed
    - .env file with required secrets (use --generate to create template)

ENVIRONMENT VARIABLES (.env file):
    API_SECRET_KEY       - Secret key for API authentication
    GITHUB_API_TOKEN         - GitHub personal access token
    GITLAB_URL           - GitLab instance URL
    GITLAB_API_TOKEN     - GitLab API token
    REDIS_URL            - External Redis URL (optional, uses internal Redis if not set)

EOF
}

# Generate .env template
generate_env_template() {
    if [[ -f "$ENV_FILE" ]]; then
        print_warning ".env file already exists at $ENV_FILE"
        read -p "Overwrite existing .env file? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env file"
            return 0
        fi
    fi

    cat > "$ENV_FILE" << 'EOF'
# GSAST Local Development Environment Variables
# Fill in the required values and remove this header

# Required: API Secret Key (generate a secure random string)
API_SECRET_KEY=

# Required: GitHub Token for repository access
GITHUB_API_TOKEN=

# Required: GitLab Configuration
GITLAB_URL=
GITLAB_API_TOKEN=


# Optional: External Redis URL (leave empty to use internal Redis)
# REDIS_URL=redis://:password@redis-host:6379
EOF

    print_success "Generated .env template at $ENV_FILE"
    print_info "Please edit the .env file and fill in the required values before deploying"
}

# Check if required tools are installed
check_requirements() {
    print_info "Checking requirements..."
    
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v helm &> /dev/null; then
        print_error "helm is not installed or not in PATH"
        exit 1
    fi
    
    # Check kubectl connection
    if ! kubectl cluster-info &> /dev/null; then
        print_error "kubectl is not connected to a cluster"
        exit 1
    fi
    
    print_success "All requirements satisfied"
}

# Check if Docker image exists
check_docker_image() {
    if [[ "$SKIP_IMAGE_CHECK" == true ]]; then
        print_info "Skipping Docker image check"
        return 0
    fi

    print_info "Checking Docker image: $DOCKER_IMAGE"
    
    # Extract repository and tag
    local image_repo="${DOCKER_IMAGE%:*}"
    local image_tag="${DOCKER_IMAGE##*:}"
    
    # Check if image exists locally
    if docker image inspect "$DOCKER_IMAGE" &> /dev/null; then
        print_success "Docker image found locally: $DOCKER_IMAGE"
        return 0
    fi
    
    # If it's the default gsast:latest image, offer to build it
    if [[ "$DOCKER_IMAGE" == "gsast:latest" ]]; then
        print_error "Docker image '$DOCKER_IMAGE' not found locally"
        print_info "This appears to be the default image. You have several options:"
        echo "  1. Build the image: $0 --build"
        echo "  2. Use a different image: $0 --image your-registry/gsast:tag"
        echo "  3. Build manually: docker build -t gsast:latest $PROJECT_ROOT"
        echo ""
        print_info "For local clusters, remember to load the image after building:"
        echo "  minikube: minikube image load gsast:latest"
        echo "  kind: kind load docker-image gsast:latest --name <cluster-name>"
        exit 1
    else
        print_warning "Docker image '$DOCKER_IMAGE' not found locally"
        print_info "Assuming it's available in a registry"
    fi
}

# Build Docker image
build_docker_image() {
    print_info "Building Docker image: $DOCKER_IMAGE"
    
    local project_root="$PROJECT_ROOT"
    
    if [[ ! -f "$project_root/Dockerfile" ]]; then
        print_error "Dockerfile not found at $project_root/Dockerfile"
        exit 1
    fi
    
    print_info "Building from: $project_root"
    
    if ! docker build -t "$DOCKER_IMAGE" "$project_root"; then
        print_error "Failed to build Docker image"
        exit 1
    fi
    
    print_success "Docker image built successfully: $DOCKER_IMAGE"
    
    # Load image into cluster if using minikube
    if kubectl config current-context | grep -q minikube; then
        print_info "Loading image into minikube cluster..."
        if ! minikube image load "$DOCKER_IMAGE"; then
            print_warning "Failed to load image into minikube. You may need to run: minikube image load $DOCKER_IMAGE"
        else
            print_success "Image loaded into minikube cluster"
        fi
    elif kubectl config current-context | grep -q kind; then
        print_info "Loading image into kind cluster..."
        local cluster_name=$(kubectl config current-context | sed 's/kind-//')
        if ! kind load docker-image "$DOCKER_IMAGE" --name "$cluster_name"; then
            print_warning "Failed to load image into kind cluster. You may need to run: kind load docker-image $DOCKER_IMAGE --name $cluster_name"
        else
            print_success "Image loaded into kind cluster"
        fi
    else
        print_info "For local clusters, you may need to load the image manually:"
        echo "  minikube: minikube image load $DOCKER_IMAGE"
        echo "  kind: kind load docker-image $DOCKER_IMAGE --name <cluster-name>"
    fi
}

# Load and validate .env file
load_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        print_error ".env file not found at $ENV_FILE"
        print_info "Use '$0 --generate' to create a template .env file"
        exit 1
    fi

    print_info "Loading environment variables from $ENV_FILE"
    
    # Load .env file
    set -a
    source "$ENV_FILE"
    set +a
    
    # Validate required variables
    local required_vars=("API_SECRET_KEY" "GITHUB_API_TOKEN" "GITLAB_URL" "GITLAB_API_TOKEN")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        print_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        print_info "Please edit $ENV_FILE and provide values for all required variables"
        exit 1
    fi
    
    print_success "Environment variables loaded and validated"
}

# Create Kubernetes secret from environment variables
create_secret() {
    print_info "Creating Kubernetes secret in namespace $NAMESPACE"
    
    # Create namespace if it doesn't exist
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    
    # Delete existing secret if it exists
    kubectl delete secret gsast-local-secret -n "$NAMESPACE" --ignore-not-found=true
    
    # Prepare secret data
    local secret_data=(
        "--from-literal=API_SECRET_KEY=$API_SECRET_KEY"
        "--from-literal=GITHUB_API_TOKEN=$GITHUB_API_TOKEN"
        "--from-literal=GITLAB_URL=$GITLAB_URL"
        "--from-literal=GITLAB_API_TOKEN=$GITLAB_API_TOKEN"
    )
    
    # Add Redis URL only if external Redis URL is provided
    # For internal Redis, the Helm template will construct the URL
    if [[ -n "$REDIS_URL" ]]; then
        secret_data+=("--from-literal=REDIS_URL=$REDIS_URL")
    fi
    
    # Create the secret
    kubectl create secret generic gsast-local-secret \
        -n "$NAMESPACE" \
        "${secret_data[@]}"
    
    print_success "Secret created successfully"
}

# Deploy Helm chart
deploy_chart() {
    print_info "Deploying GSAST Helm chart..."
    
    cd "$CHART_DIR"
    
    # Update dependencies
    helm dependency update
    
    # Extract image repository and tag
    local image_repo="${DOCKER_IMAGE%:*}"
    local image_tag="${DOCKER_IMAGE##*:}"
    
    # Determine the correct image pull policy based on cluster type
    local current_context=$(kubectl config current-context)
    local pull_policy="Never"
    if [[ "$current_context" == "docker-desktop" ]] || [[ "$current_context" == "docker-for-desktop" ]]; then
        pull_policy="IfNotPresent"
        print_info "Using imagePullPolicy: IfNotPresent for Docker Desktop"
    else
        pull_policy="Never" 
        print_info "Using imagePullPolicy: Never for local cluster"
    fi
    
    # Create values for local deployment
    cat > /tmp/local-values.yaml << EOF
# Local deployment values
existingSecret: "gsast-local-secret"

# Use internal Redis unless external URL provided
redis:
  enabled: $([ -z "$REDIS_URL" ] && echo "true" || echo "false")
useInternalRedis: $([ -z "$REDIS_URL" ] && echo "true" || echo "false")

# Local development settings
environment:
  httpProxy: null
  httpsProxy: null
  noProxy: null
  customGitlabCA:
    enabled: false

# API configuration for local access
api:
  host: null
  loadBalancerIP: null
  service:
    type: ClusterIP
    port: 5000
  ingress:
    enabled: false

# Worker configuration
worker:
  image:
    repositoryPrefix: "$image_repo"
    tag: "$image_tag"
    pullPolicy: $pull_policy
  autoscaling:
    enabled: false
    minReplicas: 1
    maxReplicas: 1
    targetCPUUtilizationPercentage: 70

# Override resource limits for local development
api:
  resources:
    limits:
      cpu: 500m
      memory: 1Gi
    requests:
      cpu: 200m
      memory: 512Mi

workerResources:
  limits:
    cpu: 1000m
    memory: 2Gi
  requests:
    cpu: 300m
    memory: 1Gi

# Disable internal-specific features
internal:
  enabled: false
  annotations: {}
  labels: {}

# Secrets are handled by existingSecret
secrets: {}
EOF

    # Deploy the chart
    if ! helm upgrade --install "$RELEASE_NAME" . \
        --namespace "$NAMESPACE" \
        --values /tmp/local-values.yaml \
        --timeout=300s \
        --wait 2>/tmp/helm-error.log; then
        
        # Check if it's a conflict error
        if grep -q "exists and cannot be imported" /tmp/helm-error.log; then
            print_error "Deployment failed due to resource conflicts"
            print_info "There are existing resources from a previous deployment"
            print_info "Run with --clean or --force to clean up existing resources"
            cat /tmp/helm-error.log
            rm -f /tmp/helm-error.log /tmp/local-values.yaml
            exit 1
        else
            print_error "Deployment failed for other reasons:"
            cat /tmp/helm-error.log
            rm -f /tmp/helm-error.log /tmp/local-values.yaml
            exit 1
        fi
    fi
    
    # Clean up temporary files
    rm -f /tmp/local-values.yaml /tmp/helm-error.log
    
    print_success "GSAST deployed successfully!"
}

# Port forward to GSAST API
# Port forward to GSAST API
port_forward_api() {
    print_info "Starting port-forward to GSAST API..."
    print_info "Service: gsast-api in namespace $NAMESPACE"

    local start_port=5000
    local max_attempts=10
    local port="$start_port"

    # Find an available local port
    for ((i = 0; i < max_attempts; i++)); do
        if ! lsof -i ":$port" &>/dev/null; then
            break
        fi
        print_warning "Port $port is in use. Trying next..."
        ((port++))
    done

    if [[ $i -eq $max_attempts ]]; then
        print_error "Failed to find a free port starting from $start_port after $max_attempts attempts"
        exit 1
    fi

    print_success "Using local port $port for forwarding"
    echo "Visit: http://localhost:$port"
    echo ""

    # Check if service exists
    if ! kubectl get service gsast-api -n "$NAMESPACE" >/dev/null 2>&1; then
        print_error "Service 'gsast-api' not found in namespace '$NAMESPACE'"
        print_info "Make sure GSAST is deployed first:"
        echo "  $0"
        exit 1
    fi

    # Start port-forwarding
    kubectl port-forward -n "$NAMESPACE" service/gsast-api "$port:5000"
}


# Show post-deployment information
show_deployment_info() {
    print_info "Deployment Information:"
    echo "  Namespace:    $NAMESPACE"
    echo "  Release:      $RELEASE_NAME"
    echo "  Chart Dir:    $CHART_DIR"
    echo ""
    
    print_info "To access the GSAST API:"
    echo "  $0 --port-forward"
    echo "  Or manually: kubectl port-forward -n $NAMESPACE service/gsast-api 5000:5000"
    echo "  Then visit: http://localhost:5000"
    echo ""
    
    print_info "Useful commands:"
    echo "  # Check pod status"
    echo "  kubectl get pods -n $NAMESPACE"
    echo ""
    echo "  # View API logs"
    echo "  kubectl logs -n $NAMESPACE -l component=gsast-api"
    echo ""
    echo "  # View worker logs"
    echo "  kubectl logs -n $NAMESPACE -l component=gsast-worker"
    echo ""
    echo "  # Uninstall"
    echo "  helm uninstall $RELEASE_NAME -n $NAMESPACE"
    echo "  kubectl delete namespace $NAMESPACE"
}

# Clean up existing deployment
cleanup_deployment() {
    print_info "Cleaning up existing deployment..."
    
    # Uninstall any helm releases in the namespace that might conflict
    local releases=$(helm list -n "$NAMESPACE" -q 2>/dev/null || true)
    if [[ -n "$releases" ]]; then
        for release in $releases; do
            print_info "Uninstalling existing release: $release"
            helm uninstall "$release" -n "$NAMESPACE"
        done
        print_success "Helm releases uninstalled"
    fi
    
    # Force delete any remaining GSAST resources that might conflict
    print_info "Cleaning up any remaining GSAST resources..."
    kubectl delete deployment,service,secret,hpa,ingress -l app.kubernetes.io/name=gsast -n "$NAMESPACE" --ignore-not-found=true
    kubectl delete secret gsast-local-secret -n "$NAMESPACE" --ignore-not-found=true
    
    # Wait a moment for resources to be fully deleted
    sleep 3
    
    print_success "Cleanup completed"
}

# Main function
main() {
    local generate_only=false
    local clean_first=false
    local force_mode=false
    local port_forward_only=false
    local delete_only=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --generate)
                generate_only=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            --port-forward|--pf)
                port_forward_only=true
                shift
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --release)
                RELEASE_NAME="$2"
                shift 2
                ;;
            --clean)
                clean_first=true
                shift
                ;;
            --force)
                clean_first=true
                force_mode=true
                shift
                ;;
            --build)
                BUILD_IMAGE=true
                shift
                ;;
            --image)
                DOCKER_IMAGE="$2"
                shift 2
                ;;
            --skip-image-check)
                SKIP_IMAGE_CHECK=true
                shift
                ;;
            --delete)
                delete_only=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                print_info "Use '$0 --help' for usage information"
                exit 1
                ;;
        esac
    done
    
    # Handle port-forward option
    if [[ "$port_forward_only" == true ]]; then
        port_forward_api
        exit 0
    fi
    
    # Handle generate option
    if [[ "$generate_only" == true ]]; then
        generate_env_template
        exit 0
    fi

    if [[ "$delete_only" == true ]]; then
        print_info "Deleting GSAST deployment and namespace: $NAMESPACE"
        helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" || print_warning "Helm release not found or already removed"
        kubectl delete namespace "$NAMESPACE" --ignore-not-found=true
        print_success "GSAST deployment and namespace deleted"
        exit 0
    fi
    
    # Main deployment flow
    print_info "Starting GSAST local deployment..."
    print_info "Chart directory: $CHART_DIR"
    print_info "Environment file: $ENV_FILE"
    print_info "Namespace: $NAMESPACE"
    print_info "Release: $RELEASE_NAME"
    echo ""
    
    check_requirements
    load_env_file
    
    # Build image if requested
    if [[ "$BUILD_IMAGE" == true ]]; then
        build_docker_image
    else
        check_docker_image
    fi
    
    if [[ "$clean_first" == true ]]; then
        if [[ "$force_mode" == true ]]; then
            print_warning "Force mode enabled - cleaning up all resources"
        fi
        cleanup_deployment
    fi
    
    create_secret
    deploy_chart
    show_deployment_info
    
    print_success "Local deployment completed successfully!"
}

# Run main function
main "$@"