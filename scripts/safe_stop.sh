#!/bin/bash
# Safe shutdown script - gracefully stops API and Docker services without crashing

set -e

echo "=================================================="
echo "Safe Shutdown - Stopping RAG Agent API"
echo "=================================================="

PORT=8000
TIMEOUT=15

# Step 1: Gracefully stop API server (SIGTERM, not SIGKILL)
echo ""
echo "Step 1: Stopping API server on port $PORT..."
PID=$(lsof -ti:$PORT 2>/dev/null || true)

if [ -n "$PID" ]; then
    echo "  Found process $PID on port $PORT"
    echo "  Sending SIGTERM (graceful shutdown)..."

    # Use SIGTERM (15) for graceful shutdown, not SIGKILL (9)
    kill -15 $PID 2>/dev/null || true

    # Wait for process to exit (up to TIMEOUT seconds)
    ELAPSED=0
    while kill -0 $PID 2>/dev/null && [ $ELAPSED -lt $TIMEOUT ]; do
        echo "  Waiting for shutdown ($ELAPSED/${TIMEOUT}s)..."
        sleep 1
        ELAPSED=$((ELAPSED + 1))
    done

    if kill -0 $PID 2>/dev/null; then
        echo "  ⚠ Process did not shutdown gracefully, force killing..."
        kill -9 $PID 2>/dev/null || true
        sleep 2
    else
        echo "  ✓ Process stopped gracefully"
        sleep 2
    fi
else
    echo "  ℹ No process running on port $PORT"
fi

# Step 2: Check port is released
echo ""
echo "Step 2: Verifying port $PORT is released..."
if lsof -ti:$PORT &>/dev/null; then
    echo "  ✗ Port still in use. Checking which process..."
    lsof -i:$PORT
else
    echo "  ✓ Port $PORT is free"
fi

# Step 3: Gracefully stop Docker containers (if desired)
echo ""
echo "Step 3: Docker containers status:"
if command -v docker-compose &>/dev/null; then
    if [ -f "docker/docker-compose.yml" ]; then
        echo "  Docker containers:"
        docker-compose -f docker/docker-compose.yml ps 2>/dev/null || echo "  (docker-compose not responding)"

        read -p "  Stop Docker containers gracefully? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "  Stopping containers gracefully..."
            docker-compose -f docker/docker-compose.yml stop --timeout=15 2>/dev/null || {
                echo "  ⚠ docker-compose stop failed, trying docker stop..."
                docker ps --format "{{.Names}}" | grep -E "rag-|milvus" | xargs -r docker stop --time=15 2>/dev/null || true
            }
            sleep 2
            echo "  ✓ Containers stopped"
        fi
    fi
else
    echo "  ℹ docker-compose not found"
fi

echo ""
echo "=================================================="
echo "✓ Safe shutdown complete"
echo "=================================================="
echo ""
echo "To restart:"
echo "  1. open -a Docker"
echo "  2. Wait 30 seconds"
echo "  3. docker-compose -f docker/docker-compose.yml up -d"
echo "  4. python api_server.py"
