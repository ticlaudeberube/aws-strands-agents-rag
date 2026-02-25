#!/bin/bash

# Quick start script for AWS Strands Agents RAG
# This script starts both Milvus and provides instructions for Ollama

set -e

echo "======================================"
echo "AWS Strands Agents RAG - Quick Start"
echo "======================================"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

# Determine docker compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    DOCKER_COMPOSE_CMD="docker compose"
fi

echo "Starting Milvus services..."
$DOCKER_COMPOSE_CMD -f docker/docker-compose.yml up -d

echo "Waiting for Milvus to be ready..."
sleep 5

# Check if Milvus is ready
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:9091/healthz > /dev/null 2>&1; then
        echo "✓ Milvus is ready!"
        break
    fi
    attempt=$((attempt + 1))
    echo "  Waiting... ($attempt/$max_attempts)"
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo "Warning: Milvus health check did not return success"
    echo "Check with: docker-compose -f docker/docker-compose.yml logs milvus"
fi

echo ""
echo "======================================"
echo "Milvus Started Successfully!"
echo "======================================"
echo ""
echo "Next: Start Ollama in a new terminal"
echo ""
echo "macOS (with Ollama installed):"
echo "  ollama serve"
echo ""
echo "Linux (with Ollama installed):"
echo "  ollama serve"
echo ""
echo "Or use Docker:"
echo "  docker run -d -p 11434:11434 ollama/ollama"
echo ""
echo "Then pull models:"
echo "  ollama pull mistral"
echo "  ollama pull all-minilm"
echo ""
echo "Finally, test the setup:"
echo "  python main.py"
echo ""
echo "Run examples:"
echo "  python examples/basic_rag.py"
echo "  python examples/interactive_chat.py"
echo ""
echo "To stop services:"
echo "  docker-compose -f docker/docker-compose.yml down"
echo ""
