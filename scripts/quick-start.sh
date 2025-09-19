#!/bin/bash
# GSAST Quick Start Script
# The fastest way to get GSAST running locally

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

show_help() {
    cat << EOF
GSAST Quick Start

Get GSAST running in under 2 minutes!

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --help          Show this help
    --setup-only    Only create configuration, don't start services
    --docker-compose Use docker-compose (simplest)
    --kubernetes    Use Kubernetes with local deployment script
    --python        Use manual Python setup
    --stop          Stop running services
    --clean         Stop and clean up everything

EXAMPLES:
    $0                        # Quick setup with docker-compose
    $0 --kubernetes           # Quick setup with Kubernetes
    $0 --python               # Quick setup with Python
    $0 --setup-only           # Just create config files
    $0 --stop                 # Stop running services
    $0 --clean                # Stop and remove everything

EOF
}

check_requirements() {
    print_info "Checking requirements..."
    
    local missing=()
    
    if ! command -v git &> /dev/null; then
        missing+=("git")
    fi
    
    if ! command -v docker &> /dev/null; then
        missing+=("docker")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        print_error "Missing required tools: ${missing[*]}"
        print_info "Please install the missing tools and try again"
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker and try again"
        return 1
    fi
    
    print_success "All requirements satisfied"
}

setup_environment() {
    print_info "Setting up environment configuration..."
    
    if [[ -f "$ENV_FILE" ]]; then
        print_info "Found existing .env file"
        return 0
    fi
    
    if [[ -f "$PROJECT_ROOT/env.example" ]]; then
        cp "$PROJECT_ROOT/env.example" "$ENV_FILE"
        print_success "Created .env file from template"
    else
        # Create basic .env if no template exists
        cat > "$ENV_FILE" << 'EOF'
# GSAST Environment Configuration

# Required: GitHub Personal Access Token
# Create at: https://github.com/settings/tokens
GITHUB_API_TOKEN=

# Required: GitLab Configuration  
GITLAB_URL=https://gitlab.com
GITLAB_API_TOKEN=

# Required: API Secret Key
API_SECRET_KEY=

# Optional: Flask environment
FLASK_ENV=development
EOF
        print_success "Created basic .env file"
    fi
    
    print_warning "IMPORTANT: You must edit .env and add your API tokens!"
    print_info "Required tokens:"
    echo "  - GITHUB_API_TOKEN: GitHub Personal Access Token (https://github.com/settings/tokens)"
    echo "  - GITLAB_API_TOKEN: GitLab Personal Access Token (GitLab Settings > Access Tokens)"
    echo "  - API_SECRET_KEY: Any secure random string"
    echo ""
    
    if command -v openssl &> /dev/null; then
        local suggested_key=$(openssl rand -base64 32)
        print_info "Suggested API_SECRET_KEY: $suggested_key"
    fi
    
    read -p "Press Enter to open .env file for editing (Ctrl+C to skip): "
    
    if command -v code &> /dev/null; then
        code "$ENV_FILE"
    elif command -v vim &> /dev/null; then
        vim "$ENV_FILE"
    elif command -v nano &> /dev/null; then
        nano "$ENV_FILE"
    else
        print_info "Please manually edit: $ENV_FILE"
    fi
}

validate_env() {
    print_info "Validating environment configuration..."
    
    if [[ ! -f "$ENV_FILE" ]]; then
        print_error ".env file not found"
        return 1
    fi
    
    source "$ENV_FILE"
    
    local missing=()
    
    if [[ -z "$GITHUB_API_TOKEN" ]]; then
        missing+=("GITHUB_API_TOKEN")
    fi
    
    if [[ -z "$GITLAB_API_TOKEN" ]]; then
        missing+=("GITLAB_API_TOKEN")  
    fi
    
    if [[ -z "$API_SECRET_KEY" ]]; then
        missing+=("API_SECRET_KEY")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        print_error "Missing required environment variables: ${missing[*]}"
        print_info "Please edit $ENV_FILE and provide values for all required variables"
        return 1
    fi
    
    print_success "Environment configuration is valid"
}

start_docker_compose() {
    print_info "Starting GSAST with Docker Compose..."
    
    cd "$PROJECT_ROOT"
    
    if [[ ! -f "docker-compose.yml" ]]; then
        print_error "docker-compose.yml not found in project root"
        return 1
    fi
    
    # Pull latest images and build
    docker-compose pull redis
    docker-compose build --no-cache
    
    # Start services
    docker-compose up -d
    
    print_success "GSAST started with Docker Compose!"
    print_info "Services starting up... this may take a moment"
    
    # Wait for API to be ready
    print_info "Waiting for API server to be ready..."
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if curl -s http://localhost:5000/health &> /dev/null; then
            break
        fi
        sleep 2
        ((retries--))
        echo -n "."
    done
    echo ""
    
    if [[ $retries -eq 0 ]]; then
        print_warning "API server didn't respond in time, but services are starting"
        print_info "Check logs with: docker-compose logs -f"
    else
        print_success "API server is ready!"
    fi
    
    show_access_info
}

start_kubernetes() {
    print_info "Starting GSAST with Kubernetes..."
    
    local deploy_script="$PROJECT_ROOT/scripts/deploy-local.sh"
    
    if [[ ! -f "$deploy_script" ]]; then
        print_error "Deploy script not found: $deploy_script"
        return 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl not found. Please install kubectl for Kubernetes deployment"
        return 1
    fi
    
    if ! command -v helm &> /dev/null; then
        print_error "helm not found. Please install Helm for Kubernetes deployment"
        return 1
    fi
    
    # Use the existing deployment script
    "$deploy_script" --build
    
    print_success "GSAST deployed to Kubernetes!"
    print_info "To access the API, run:"
    echo "  $deploy_script --port-forward"
}

start_python() {
    print_info "Starting GSAST with Python (manual setup)..."
    
    cd "$PROJECT_ROOT/gsast"
    
    # Check if virtual environment exists
    if [[ ! -d "venv" ]]; then
        print_info "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    
    print_info "Installing Python dependencies..."
    pip install -e .
    
    # Start Redis if needed
    if ! redis-cli ping &> /dev/null; then
        print_info "Starting Redis..."
        if command -v brew &> /dev/null; then
            brew services start redis || docker run -d -p 6379:6379 redis:7-alpine
        else
            docker run -d -p 6379:6379 redis:7-alpine
        fi
    fi
    
    source "$ENV_FILE"
    export REDIS_URL="redis://localhost:6379"
    
    print_info "Starting API server and worker..."
    python api_server.py &
    API_PID=$!
    
    python worker.py &
    WORKER_PID=$!
    
    echo "$API_PID" > .api.pid
    echo "$WORKER_PID" > .worker.pid
    
    print_success "GSAST started with Python!"
    print_info "API PID: $API_PID, Worker PID: $WORKER_PID"
    
    show_access_info
}

show_access_info() {
    echo ""
    print_success "🚀 GSAST is running!"
    echo ""
    print_info "Access the API:"
    echo "  📖 API Documentation: http://localhost:5000/apidocs/"
    echo "  🔍 Health Check: http://localhost:5000/health"
    echo "  📊 API Endpoints: http://localhost:5000/"
    echo ""
    print_info "Example CLI usage:"
    echo "  cd gsast/"
    echo "  python cli_client.py --help"
    echo "  python cli_client.py scan rules/sg_custom/"
    echo ""
    print_info "Stop services:"
    echo "  $0 --stop"
}

stop_services() {
    print_info "Stopping GSAST services..."
    
    # Stop docker-compose if running
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        cd "$PROJECT_ROOT"
        docker-compose stop &> /dev/null || true
        print_info "Stopped Docker Compose services"
    fi
    
    # Stop Python processes
    if [[ -f "$PROJECT_ROOT/gsast/.api.pid" ]]; then
        local api_pid=$(cat "$PROJECT_ROOT/gsast/.api.pid")
        kill $api_pid &> /dev/null || true
        rm -f "$PROJECT_ROOT/gsast/.api.pid"
        print_info "Stopped API server (PID: $api_pid)"
    fi
    
    if [[ -f "$PROJECT_ROOT/gsast/.worker.pid" ]]; then
        local worker_pid=$(cat "$PROJECT_ROOT/gsast/.worker.pid")
        kill $worker_pid &> /dev/null || true
        rm -f "$PROJECT_ROOT/gsast/.worker.pid"
        print_info "Stopped worker (PID: $worker_pid)"
    fi
    
    print_success "GSAST services stopped"
}

clean_all() {
    print_info "Cleaning up GSAST..."
    
    stop_services
    
    # Clean docker-compose
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        cd "$PROJECT_ROOT"
        docker-compose down -v --remove-orphans &> /dev/null || true
        print_info "Cleaned Docker Compose resources"
    fi
    
    # Clean Kubernetes deployment
    if command -v kubectl &> /dev/null; then
        local deploy_script="$PROJECT_ROOT/scripts/deploy-local.sh"
        if [[ -f "$deploy_script" ]]; then
            "$deploy_script" --delete &> /dev/null || true
            print_info "Cleaned Kubernetes deployment"
        fi
    fi
    
    print_success "Cleanup completed"
}

main() {
    local setup_only=false
    local method="docker-compose"
    local stop_services_flag=false
    local clean_flag=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                exit 0
                ;;
            --setup-only)
                setup_only=true
                shift
                ;;
            --docker-compose)
                method="docker-compose"
                shift
                ;;
            --kubernetes)
                method="kubernetes"  
                shift
                ;;
            --python)
                method="python"
                shift
                ;;
            --stop)
                stop_services_flag=true
                shift
                ;;
            --clean)
                clean_flag=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    if [[ "$stop_services_flag" == true ]]; then
        stop_services
        exit 0
    fi
    
    if [[ "$clean_flag" == true ]]; then
        clean_all
        exit 0
    fi
    
    echo "🚀 GSAST Quick Start"
    echo "=================="
    
    check_requirements
    setup_environment
    
    if [[ "$setup_only" == true ]]; then
        print_success "Setup completed! Edit .env file and run again to start services"
        exit 0
    fi
    
    validate_env
    
    case $method in
        docker-compose)
            start_docker_compose
            ;;
        kubernetes)
            start_kubernetes
            ;;
        python)
            start_python
            ;;
        *)
            print_error "Unknown method: $method"
            exit 1
            ;;
    esac
}

main "$@"
