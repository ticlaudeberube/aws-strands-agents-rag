# API Port Configuration Strategy

## Overview

This document clarifies the API_PORT usage across the project, explains how to handle port conflicts during local development, and describes the .env file architecture.

## Current Configuration

### Default Ports

| Component | Port | Environment | Purpose |
|-----------|------|-------------|---------|
| RAG API Server | **8000** | Docker + Local | Main API endpoint |
| React Chatbot | **3000** | Local (npm) | Frontend development server |
| Milvus Vector DB | **19530** | Docker | Vector database gRPC |
| Milvus WebUI | **9091** | Docker | Vector database web interface |
| MinIO Console | **9001** | Docker | Object storage admin |

## .env File Architecture

### Root .env (api_server.py & Python modules)
**Location:** `/Users/claude/Documents/workspace/aws-strands-agents-rag/.env`

Controls the **Python backend** (RAG API Server):
```env
# API Server Configuration
API_PORT=8000
```

**Used by:**
- `api_server.py` - Starts uvicorn on `API_PORT`
- `src/tools/*` - Other backend services
- Docker compose passes this to the container

### React Chatbot .env (front-end only)
**Location:** `/Users/claude/Documents/workspace/aws-strands-agents-rag/chatbots/react-chatbot/.env`

Controls the **React frontend** (development):
```env
REACT_APP_API_PORT=8000
REACT_APP_API_HOST=localhost
```

**Used by:**
- `chatbots/react-chatbot/src/App.js` - Connects to backend API
- React environment variables (prefixed with `REACT_APP_`)

## Local Development (Port Conflict Resolution)

### Scenario 1: Running API Locally (Not in Docker)

**If port 8000 is already in use:**

1. **Option A: Change API port to 8001**
   ```bash
   # In root .env
   API_PORT=8001
   
   # Start API server
   python api_server.py
   # Server runs on http://localhost:8001
   ```

2. **Update React frontend to match:**
   ```bash
   # In chatbots/react-chatbot/.env
   REACT_APP_API_PORT=8001
   
   # Start React app
   cd chatbots/react-chatbot
   npm start
   # Frontend connects to http://localhost:8001
   ```

### Scenario 2: Running API in Docker (Recommended)

**Port 8000 conflicts with another service:**

1. **Option A: Shutdown conflicting service**
   ```bash
   # Identify what's using port 8000
   lsof -i :8000
   
   # Shutdown the conflicting service
   # Example: Kill local API server
   pkill -f "python api_server.py"
   ```

2. **Option B: Use different external port in docker-compose**
   ```yaml
   # docker/docker-compose.yml
   rag-api:
     ports:
       - "8001:8000"  # External:Internal
     environment:
       - API_PORT=8000
   ```
   API still listens on 8000 internally, but exposed as 8001 on host.

   Update frontend:
   ```bash
   # chatbots/react-chatbot/.env
   REACT_APP_API_PORT=8001
   ```

## Recommended Development Setup

### For Docker-Based Development (Recommended)

**Best practice: Keep consistent ports for simplicity**

```bash
# 1. Ensure Docker is running and containers are up
cd docker
docker compose up -d

# 2. API automatically runs on port 8000
# (configured in docker-compose.yml)

# 3. Start React frontend (in separate terminal)
cd chatbots/react-chatbot
REACT_APP_API_PORT=8000 npm start
```

### For Local Python Development (No Docker)

```bash
# 1. Make sure no Docker containers are using port 8000
docker compose down

# 2. Update root .env if needed
# API_PORT=8000 (or different if conflicting)

# 3. Start API server
python api_server.py
# Output: Uvicorn running on http://0.0.0.0:8000

# 4. In another terminal, start React
cd chatbots/react-chatbot
npm start
```

## Configuration Hierarchy

### Python (api_server.py)
1. Environment variable: `API_PORT` (from .env)
2. Fallback: Hard-coded `8000` in `src/config/settings.py`
3. Docker passes: `API_PORT=8000` in docker-compose.yml

### React (App.js)
1. Environment variable: `REACT_APP_API_PORT` (from .env)
2. Fallback: Hard-coded `'8000'` in `chatbots/react-chatbot/src/App.js`
3. Can be overridden at runtime: `REACT_APP_API_PORT=8001 npm start`

## Migration Guide: Docker Workflow

If transitioning from local to Docker development:

```bash
# Step 1: Ensure .env files are in sync
# Root .env: API_PORT=8000
# react-chatbot/.env: REACT_APP_API_PORT=8000

# Step 2: Build and start Docker containers
cd docker
docker compose up -d

# Step 3: Verify API is running
docker exec rag-api curl http://localhost:8000/health

# Step 4: Start React frontend (separate terminal)
cd chatbots/react-chatbot
npm start
# Connects to http://localhost:8000 (from .env)
```

## Troubleshooting

### "Port 8000 is already in use"

**Docker error:**
```bash
# Find what's using the port
lsof -i :8000

# Option 1: Kill the process
kill -9 <PID>

# Option 2: Use different external port
# Edit docker/docker-compose.yml
rag-api:
  ports:
    - "9000:8000"  # Use 9000 instead

# Update React .env accordingly
REACT_APP_API_PORT=9000
```

**Python error:**
```bash
# Change port in .env
API_PORT=8001

# Restart API server
python api_server.py  # Runs on 8001
```

### React can't connect to API

**Check:**
1. `chatbots/react-chatbot/.env` has correct `REACT_APP_API_PORT`
2. Python API is actually running on that port
3. Both are using same port

```bash
# Verify API health
curl http://localhost:8000/health

# Check React env variable
grep REACT_APP_API_PORT chatbots/react-chatbot/.env
```

### Docker API container unhealthy

```bash
# Check logs
docker logs rag-api

# Verify environment variable was passed
docker exec rag-api printenv API_PORT

# Restart container
docker compose restart rag-api
```

## Best Practices

1. **Use consistent ports across .env files**
   - Root `.env`: `API_PORT=8000`
   - React `.env`: `REACT_APP_API_PORT=8000`

2. **In Docker, keep internal port fixed**
   - Internal: `API_PORT=8000`
   - External: Can vary in docker-compose.yml (e.g., `8001:8000`)

3. **Document custom port changes**
   - When changing to non-standard port (not 8000), document in comments
   - Update both .env files together

4. **Check port availability before deployment**
   ```bash
   # macOS/Linux
   lsof -i :8000
   
   # Windows
   netstat -ano | findstr :8000
   ```

5. **Health checks verify correct port**
   ```bash
   # Docker
   docker logs rag-api | grep "Uvicorn running"
   
   # Local
   curl http://localhost:8000/health
   ```

## Summary

- **Single root `.env`** for Python backend configuration
- **Separate `.env` per sub-project** for frontend/tooling
- **Port 8000** is default, but can be changed
- **Docker-based development recommended** (avoids local port conflicts)
- **Test connectivity** with curl health checks

