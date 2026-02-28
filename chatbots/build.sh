#!/bin/bash

###############################################################################
# React Chatbot Build & Deployment Helper Script
#
# Supports:
# - Local development (npm start)
# - Docker build and run
# - Production build optimization
###############################################################################

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_DIR="$(dirname "$0")"
REACT_DIR="$APP_DIR/react-chatbot"

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
# Local Development
###############################################################################

run_dev() {
    log_info "Starting React development server..."
    
    cd "$REACT_DIR"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        log_info "Installing dependencies..."
        npm install
    fi
    
    log_success "Starting development server on http://localhost:3000"
    log_info "Press Ctrl+C to stop"
    
    npm start
}

###############################################################################
# Production Build
###############################################################################

build_production() {
    log_info "Building React app for production..."
    
    cd "$REACT_DIR"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log_info "Installing dependencies..."
        npm install
    fi
    
    # Build
    log_info "Building optimized production bundle..."
    npm run build
    
    log_success "Production build complete!"
    log_info "Output location: $REACT_DIR/build"
    log_info "Build size: $(du -sh "$REACT_DIR/build" | cut -f1)"
    
    # Show recommended next steps
    echo ""
    echo "Next steps:"
    echo "  1. Docker:    docker build -f docker/Dockerfile.react -t rag-react:latest ."
    echo "  2. S3:        aws s3 sync build/ s3://bucket-name/"
    echo "  3. Local:     python -m http.server 3000 --directory build/"
}

###############################################################################
# Docker Build & Run
###############################################################################

build_docker() {
    log_info "Building React Docker image..."
    
    cd "$(dirname "$APP_DIR")"  # Go to project root
    
    docker build \
        -f docker/Dockerfile.react \
        -t rag-react:latest \
        -t rag-react:prod \
        .
    
    log_success "Docker image built: rag-react:latest"
}

run_docker_standalone() {
    log_info "Running React container (standalone)..."
    
    # Build if not exists
    if ! docker images | grep -q "rag-react"; then
        build_docker
    fi
    
    docker run \
        --name rag-react \
        -p 3000:3000 \
        -e REACT_APP_API_PORT=8000 \
        -e REACT_APP_API_HOST=host.docker.internal \
        --rm \
        rag-react:latest
    
    log_success "React app running on http://localhost:3000"
}

run_docker_compose() {
    log_info "Starting all services with Docker Compose..."
    
    cd "$(dirname "$APP_DIR")/docker"
    
    if ! docker compose config > /dev/null 2>&1; then
        log_error "docker-compose.yml is invalid or docker compose not available"
        return 1
    fi
    
    log_info "Building React service..."
    docker compose build react-chatbot
    
    log_info "Starting all services..."
    docker compose up -d
    
    log_success "Services started!"
    echo ""
    echo "  React:       http://localhost:3000"
    echo "  API:         http://localhost:8000"
    echo "  Milvus:      http://localhost:19530"
    echo "  Milvus UI:   http://localhost:9091"
    echo "  MinIO:       http://localhost:9001"
    echo ""
    echo "View logs: docker compose logs -f react-chatbot"
    echo "Stop all:  docker compose down"
}

###############################################################################
# Utilities
###############################################################################

check_api() {
    log_info "Checking API server health..."
    
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_success "API is healthy ✓"
        curl -s http://localhost:8000/health | python3 -m json.tool
        return 0
    else
        log_warning "API is not responding on port 8000"
        log_info "Make sure the API server is running:"
        log_info "  python api_server.py"
        return 1
    fi
}

check_react() {
    log_info "Checking React app..."
    
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        log_success "React app is running ✓"
        return 0
    else
        log_warning "React app is not responding on port 3000"
        return 1
    fi
}

health_check() {
    log_info "Running health checks..."
    echo ""
    
    check_api || true
    echo ""
    check_react || true
}

cleanup_docker() {
    log_info "Cleaning up Docker resources..."
    
    # Stop containers
    docker compose down 2>/dev/null || true
    
    # Remove React image
    docker rmi rag-react:latest 2>/dev/null || true
    docker rmi rag-react:prod 2>/dev/null || true
    
    log_success "Cleanup complete"
}

###############################################################################
# Usage
###############################################################################

show_usage() {
    cat << 'EOF'
React Chatbot Management Script

Usage: ./chatbots/build.sh [COMMAND]

Commands:
  dev              Start development server (npm start)
  build            Build production bundle
  docker           Build Docker image
  docker-run       Run Docker container (standalone)
  compose          Run with Docker Compose (full stack)
  check            Health check (API + React)
  clean            Clean up Docker resources
  help, -h, --help Show this help message

Examples:
  # Development
  ./chatbots/build.sh dev

  # Production build
  ./chatbots/build.sh build

  # Docker deployment
  ./chatbots/build.sh docker
  ./chatbots/build.sh docker-run

  # Full stack with Docker Compose
  ./chatbots/build.sh compose

  # Health checks
  ./chatbots/build.sh check

EOF
}

###############################################################################
# Main
###############################################################################

main() {
    # Default to help if no argument
    COMMAND="${1:-help}"
    
    case "$COMMAND" in
        dev)
            run_dev
            ;;
        build)
            build_production
            ;;
        docker)
            build_docker
            ;;
        docker-run)
            run_docker_standalone
            ;;
        compose)
            run_docker_compose
            ;;
        check)
            health_check
            ;;
        clean)
            cleanup_docker
            ;;
        help|-h|--help)
            show_usage
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
