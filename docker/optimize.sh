#!/bin/bash

###############################################################################
# RAG Application Docker Performance Optimization Script
#
# This script optimizes Docker and system settings for the RAG application
# with Milvus, MinIO, and etcd services.
###############################################################################

# Use set +e to handle errors gracefully
set +e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  ${1}${NC}"
}

log_success() {
    echo -e "${GREEN}✅ ${1}${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  ${1}${NC}"
}

log_error() {
    echo -e "${RED}❌ ${1}${NC}"
}

###############################################################################
# Main Optimization Functions
###############################################################################

optimize_docker_desktop() {
    log_info "Configuring Docker Daemon..."

    local DOCKER_CONFIG="${HOME}/.docker"
    local DAEMON_JSON="${DOCKER_CONFIG}/daemon.json"
    local SCRIPT_DIR="$(dirname "$0")"
    local SOURCE_DAEMON="${SCRIPT_DIR}/daemon.json"

    # Create Docker config directory if it doesn't exist
    mkdir -p "$DOCKER_CONFIG"

    # Check if source daemon.json exists
    if [ ! -f "$SOURCE_DAEMON" ]; then
        log_warning "daemon.json template not found, skipping daemon configuration"
        return 0
    fi

    # Backup existing daemon.json if it exists
    if [ -f "$DAEMON_JSON" ]; then
        log_warning "Backing up existing daemon.json to daemon.json.bak"
        cp "$DAEMON_JSON" "${DAEMON_JSON}.bak" 2>/dev/null || log_warning "Could not backup daemon.json"
    fi

    # Copy optimized daemon.json
    cp "$SOURCE_DAEMON" "$DAEMON_JSON" 2>/dev/null
    if [ $? -eq 0 ]; then
        log_success "Docker daemon configuration updated"
    else
        log_warning "Could not update daemon.json (may need approval in Docker Desktop)"
    fi
}

optimize_system_macos() {
    log_info "Optimizing macOS system settings..."

    # Note: These settings may require admin privileges
    # They're informational for macOS users

    cat << 'EOF'

For macOS, we recommend configuring Docker Desktop settings manually:

1. Open Docker Desktop Preferences (⌘ + ,)
2. Go to Resources tab and set:
   - CPUs: 8 (or more if available)
   - Memory: 16 GB (or more for better performance)
   - Swap: 2 GB
   - Disk image size: 100 GB (or more)

3. Go to Features in development tab:
   - Enable VirtioFS (faster than osxfs)
   - Enable Rosetta 2 (if using Apple Silicon)

4. Go to File Sharing and ensure project directory is shared

EOF

    log_success "macOS optimization recommendations displayed"
}

optimize_system_linux() {
    log_info "Optimizing Linux system settings..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log_warning "Some optimizations require sudo privileges. Attempting to run with sudo..."
    fi

    # Increase file descriptors
    log_info "Setting file descriptor limits..."
    echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf > /dev/null 2>&1 || true
    echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf > /dev/null 2>&1 || true

    # Memory settings
    log_info "Optimizing memory settings..."
    echo "vm.swappiness=1" | sudo tee -a /etc/sysctl.conf > /dev/null 2>&1 || true
    echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf > /dev/null 2>&1 || true

    # Network optimization
    log_info "Optimizing network settings..."
    echo "net.ipv4.tcp_tw_reuse=1" | sudo tee -a /etc/sysctl.conf > /dev/null 2>&1 || true
    echo "net.ipv4.tcp_max_syn_backlog=8096" | sudo tee -a /etc/sysctl.conf > /dev/null 2>&1 || true

    # Apply settings
    sudo sysctl -p > /dev/null 2>&1 || true

    log_success "Linux system settings optimized"
}

cleanup_docker() {
    log_info "Cleaning up Docker resources (pruning unused items)..."

    # Remove unused containers, networks, images, and build cache
    if docker system prune -f > /dev/null 2>&1; then
        log_success "Docker cleanup completed"
    else
        log_warning "Docker cleanup had warnings (this is usually safe to ignore)"
    fi

    # Optionally remove unused volumes (commented out to be safe)
    # docker volume prune -f
}

start_containers() {
    log_info "Starting optimized containers..."

    local COMPOSE_DIR="$(dirname "$0")"
    local DOCKER_COMPOSE_CMD

    # Change to docker directory
    cd "$COMPOSE_DIR" || return 1

    # Detect docker compose command (prefer 'docker compose' over 'docker-compose')
    if command -v docker &> /dev/null && docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
    else
        log_error "docker compose not found. Please install Docker Desktop or docker-compose."
        return 1
    fi

    # Check if docker daemon is working
    if ! docker ps > /dev/null 2>&1; then
        log_error "Docker daemon is not responding. Please start Docker Desktop and try again."
        return 1
    fi

    # Stop existing containers (without causing errors if they don't exist)
    log_info "Stopping existing containers..."
    $DOCKER_COMPOSE_CMD down 2>/dev/null || log_warning "No running containers to stop"

    # Wait a bit for cleanup
    sleep 2

    # Start new containers
    log_info "Starting containers with docker compose..."
    if $DOCKER_COMPOSE_CMD up -d; then
        log_success "Containers started successfully"
        return 0
    else
        log_error "Failed to start containers"
        log_error "Troubleshooting: Check that Docker Desktop is running and docker-compose.yml is valid"
        log_error "  Try manually: $DOCKER_COMPOSE_CMD -f docker-compose.yml up -d"
        return 1
    fi
}

show_service_info() {
    log_info "RAG Application Services Information:"

    cat << 'EOF'

Services:
  - Milvus Vector DB:    http://localhost:19530
  - Milvus Web UI:       http://localhost:9091/webui
  - MinIO Console:       http://localhost:9001
  - RAG API Server:      http://localhost:8000

Container Services:
  - rag-etcd (etcd)      - Configuration and metadata storage
  - rag-minio (MinIO)    - Object storage
  - rag-milvus (Milvus)  - Vector database
  - rag-api (RAG API)    - API server

Useful Commands:
  - View service logs:   docker compose logs -f [service]
  - Monitor resources:   docker stats
  - Check service health: docker compose ps
  - Stop services:       docker compose down

EOF
}

show_performance_monitoring() {
    log_info "Performance Monitoring Commands:"

    cat << 'EOF'

Real-time monitoring:
  docker stats

Service-specific logs:
  docker compose logs -f milvus
  docker compose logs -f rag-api
  docker compose logs -f minio

Health check:
  curl http://localhost:8000/health
  curl http://localhost:19530/health

View resource allocation:
  docker inspect rag-milvus --format='{{json .HostConfig.Memory}}' | python3 -m json.tool
  docker inspect rag-minio --format='{{json .HostConfig.Memory}}' | python3 -m json.tool

EOF
}

show_usage() {
    cat << 'EOF'
Usage: ./optimize.sh [OPTION]

Performance optimization script for RAG Docker application.

Options:
  -h, --help             Show this help message
  -d, --daemon           Configure Docker daemon settings
  -s, --system           Optimize system settings (Linux only)
  -c, --cleanup          Clean up Docker resources
  -x, --macos            macOS optimization recommendations
  -l, --linux            Linux system optimization
  -a, --all              Run all optimizations and start containers
  --start                Start containers with existing configuration
  --info                 Show service information
  --monitor              Show performance monitoring commands

Examples:
  ./optimize.sh --all              # Full optimization and start
  ./optimize.sh --start            # Just start containers
  ./optimize.sh --daemon           # Just configure Docker daemon
  ./optimize.sh --monitor          # Show monitoring commands

EOF
}

###############################################################################
# Main Script
###############################################################################

main() {
    log_info "RAG Application Docker Optimization"
    log_info "===================================="

    # Default to showing usage if no arguments
    if [ $# -eq 0 ]; then
        show_usage
        exit 0
    fi

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -d|--daemon)
                optimize_docker_desktop
                ;;
            -x|--macos)
                optimize_system_macos
                ;;
            -l|--linux)
                optimize_system_linux
                ;;
            -c|--cleanup)
                cleanup_docker
                ;;
            -a|--all)
                log_info "Running full optimization sequence..."

                # Try daemon config but don't fail if it doesn't work
                optimize_docker_desktop
                log_info "Waiting for potential Docker daemon restart (if applied)..."
                sleep 3

                # Detect OS and apply system optimizations
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    optimize_system_macos
                elif [[ "$OSTYPE" == "linux"* ]]; then
                    optimize_system_linux
                fi

                # Clean up and start
                cleanup_docker
                start_containers

                if [ $? -eq 0 ]; then
                    sleep 5
                    show_service_info
                    log_success "Optimization script completed successfully!"
                else
                    log_error "Failed to start containers"
                    log_error "Common fixes:"
                    log_error "  1. Ensure Docker Desktop is running"
                    log_error "  2. Check: docker ps"
                    log_error "  3. Try: docker compose -f docker-compose.yml up -d"
                    exit 1
                fi
                ;;
            --start)
                start_containers
                if [ $? -eq 0 ]; then
                    sleep 5
                    show_service_info
                else
                    exit 1
                fi
                ;;
            --info)
                show_service_info
                ;;
            --monitor)
                show_performance_monitoring
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
        shift
    done
}

main "$@"
