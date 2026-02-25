#!/bin/bash

###############################################################################
# Docker Migration Script
# 
# Migrates from milvus-standalone to the optimized Docker setup
# in aws-strands-agents-rag/docker
###############################################################################

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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
# Main Migration
###############################################################################

main() {
    log_info "Docker Migration Script"
    log_info "======================="
    
    # Check we're in the right directory
    if [ ! -f "pyproject.toml" ]; then
        log_error "Please run this script from the aws-strands-agents-rag root directory"
        exit 1
    fi
    
    if [ ! -f ".env" ]; then
        log_error ".env file not found. Please copy from .env.example first"
        exit 1
    fi
    
    if [ ! -d "docker" ]; then
        log_error "docker/ directory not found. Create it first"
        exit 1
    fi
    
    echo
    log_info "Step 1: Stopping current milvus-standalone services..."
    
    if [ -d "../milvus-standalone" ]; then
        cd ../milvus-standalone
        
        if [ -f "docker-compose.yml" ]; then
            log_info "Found milvus-standalone, stopping services..."
            docker-compose down 2>/dev/null || true
            log_success "Services stopped"
        else
            log_warning "docker-compose.yml not found in milvus-standalone"
        fi
        
        cd ../aws-strands-agents-rag
    else
        log_warning "milvus-standalone directory not found (already removed?)"
    fi
    
    echo
    log_info "Step 2: Cleaning up Docker resources..."
    docker system prune -f > /dev/null 2>&1 || true
    log_success "Docker cleanup completed"
    
    echo
    log_info "Step 3: Starting new optimized Docker services..."
    cd docker
    
    if [ ! -x "optimize.sh" ]; then
        chmod +x optimize.sh
    fi
    
    # Run optimization and start
    ./optimize.sh --all
    
    cd ..
    
    echo
    log_success "Migration completed!"
    echo
    log_info "Next steps:"
    echo "  1. Verify services: cd docker && docker-compose ps"
    echo "  2. Check collection: python scripts/verify_collection.py"
    echo "  3. Load data if needed: python document-loaders/load_milvus_docs_ollama.py"
    echo "  4. Test system: python scripts/check_setup.py"
    echo
    log_info "Services are running at:"
    echo "  Milvus: localhost:19530"
    echo "  Milvus UI: http://localhost:9091/webui"
    echo "  MinIO: http://localhost:9001"
    echo "  RAG API: http://localhost:8000"
    echo
}

main "$@"
