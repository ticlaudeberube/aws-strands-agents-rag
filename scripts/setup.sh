#!/bin/bash

# Setup script for AWS Strands Agents RAG

set -e

echo "==================================="
echo "AWS Strands Agents RAG Setup"
echo "==================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Python version: $python_version"

if [[ "$python_version" < "3.10" ]]; then
    echo "Error: Python 3.10+ is required"
    exit 1
fi

# Check Docker
echo ""
echo "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi
echo "Docker is installed"

# Check Docker Compose
echo "Checking Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    echo "Warning: docker-compose command not found, trying 'docker compose'..."
    if ! docker compose version &> /dev/null; then
        echo "Error: Docker Compose is not installed"
        exit 1
    fi
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi
echo "Docker Compose is available: $DOCKER_COMPOSE_CMD"

# Check Ollama
echo ""
echo "Checking Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "Warning: Ollama is not in PATH"
    echo "Please download from https://ollama.ai and install"
else
    echo "Ollama is installed"
fi

# Setup Python environment
echo ""
echo "Setting up Python environment..."

# Check for UV
if command -v uv &> /dev/null; then
    echo "Using UV for package installation..."
    uv pip install -e .
else
    echo "Using pip for package installation..."
    pip install -e .
fi

echo ""
echo "Installing development dependencies..."
pip install -e ".[dev]"

# Create .env file if it doesn't exist
echo ""
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ Created .env (update with your configuration)"
else
    echo "✓ .env file already exists"
fi

# Summary
echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Start Milvus:"
echo "   $DOCKER_COMPOSE_CMD -f docker/docker-compose.yml up -d"
echo ""
echo "2. Start Ollama (in a separate terminal):"
echo "   ollama serve"
echo ""
echo "3. Pull Ollama models (in another terminal):"
echo "   ollama pull qwen2.5:0.5b"
echo "   ollama pull nomic-embed-text:v1.5"
echo ""
echo "4. Run examples:"
echo "   python examples/basic_rag.py"
echo "   python examples/interactive_chat.py"
echo ""
echo "Documentation: see README.md"
echo ""
