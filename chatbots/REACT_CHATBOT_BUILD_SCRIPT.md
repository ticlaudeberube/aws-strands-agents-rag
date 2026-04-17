# React Chatbot Build Script Documentation

**Location**: `chatbots/build.sh`
**Purpose**: Comprehensive React chatbot build and deployment helper script
**Status**: ✅ Production-ready

## Overview

The `build.sh` script provides a unified interface for React chatbot development, testing, and deployment workflows. It supports local development, production builds, Docker containerization, and health monitoring.

## Usage

```bash
# Basic syntax
./chatbots/build.sh [COMMAND]

# View all commands
./chatbots/build.sh help
```

## Commands Reference

### 🔧 **Development Commands**

#### `dev` - Local Development Server
```bash
./chatbots/build.sh dev
```
- **Purpose**: Start React development server for local development
- **Features**:
  - Auto-detects and installs npm dependencies if missing
  - Starts server on http://localhost:3000
  - Hot-reload enabled for development
- **Use Case**: Daily development workflow

#### `build` - Production Build
```bash
./chatbots/build.sh build
```
- **Purpose**: Create optimized production bundle
- **Features**:
  - Installs dependencies if needed
  - Builds optimized, minified React bundle
  - Reports build size
  - Provides next deployment step suggestions
- **Output**: `react-chatbot/build/` directory
- **Use Case**: Prepare for production deployment

### 🐳 **Docker Commands**

#### `docker` - Build Docker Image
```bash
./chatbots/build.sh docker
```
- **Purpose**: Build Docker image for React chatbot
- **Features**:
  - Uses `docker/Dockerfile.react`
  - Creates tags: `rag-react:latest` and `rag-react:prod`
  - Builds from project root for proper context
- **Use Case**: Container preparation for deployment

#### `docker-run` - Run Standalone Container
```bash
./chatbots/build.sh docker-run
```
- **Purpose**: Run React app in standalone Docker container
- **Features**:
  - Auto-builds image if not present
  - Maps port 3000:3000
  - Sets environment variables for API connection
  - Uses `host.docker.internal` for local API access
- **Use Case**: Test containerized React app locally

#### `compose` - Full Stack with Docker Compose
```bash
./chatbots/build.sh compose
```
- **Purpose**: Start complete application stack
- **Features**:
  - Validates docker-compose.yml configuration
  - Builds React service
  - Starts all services in background
  - Provides service URLs and management commands
- **Services Started**:
  - React: http://localhost:3000
  - API: http://localhost:8000
  - Milvus: http://localhost:19530
  - Milvus UI: http://localhost:9091
  - MinIO: http://localhost:9001
- **Use Case**: Full development/testing environment

### ⚕️ **Monitoring Commands**

#### `check` - Health Check Suite
```bash
./chatbots/build.sh check
```
- **Purpose**: Comprehensive health monitoring
- **Features**:
  - Tests API server connectivity (port 8000)
  - Tests React app accessibility (port 3000)
  - JSON-formatted health response display
  - Non-blocking error handling
- **Use Case**: System health validation, troubleshooting

### 🧹 **Utility Commands**

#### `clean` - Docker Cleanup
```bash
./chatbots/build.sh clean
```
- **Purpose**: Clean up Docker resources
- **Features**:
  - Stops Docker Compose services
  - Removes React Docker images
  - Safe cleanup with error handling
- **Use Case**: Disk space management, fresh starts

## Technical Features

### **Smart Dependency Management**
- Auto-detects missing `node_modules`
- Runs `npm install` only when needed
- Prevents unnecessary reinstallation

### **Error Handling & Logging**
- Color-coded output with emoji indicators:
  - 🔵 `log_info`: Informational messages
  - ✅ `log_success`: Success confirmations
  - ⚠️ `log_warning`: Warning notifications
  - ❌ `log_error`: Error messages
- `set -e`: Exit on any command failure
- Graceful error recovery where appropriate

### **Environment Configuration**
```bash
# Docker environment variables
REACT_APP_API_PORT=8000
REACT_APP_API_HOST=host.docker.internal
```

### **Path Management**
- Dynamic path resolution using `dirname "$0"`
- Consistent working directory handling
- Cross-platform compatibility

## Implementation Details

### **Directory Structure**
```
chatbots/
├── build.sh           # This script
└── react-chatbot/     # React application
    ├── package.json
    ├── src/
    └── build/         # Production build output
```

### **Docker Integration**
- Uses `docker/Dockerfile.react` from project root
- Integrates with existing Docker Compose setup
- Supports both standalone and orchestrated deployments

### **Health Check Logic**
```bash
# API Health Check
curl -s http://localhost:8000/health > /dev/null 2>&1

# React App Check
curl -s http://localhost:3000 > /dev/null 2>&1
```

## Common Workflows

### **Daily Development**
1. Start API server: `python api_server.py`
2. Start React dev: `./chatbots/build.sh dev`
3. Health check: `./chatbots/build.sh check`

### **Production Deployment**
1. Build: `./chatbots/build.sh build`
2. Docker: `./chatbots/build.sh docker`
3. Deploy: Follow suggested next steps

### **Full Stack Testing**
1. Start stack: `./chatbots/build.sh compose`
2. Run tests: Access services via provided URLs
3. Monitor: `docker compose logs -f react-chatbot`
4. Cleanup: `./chatbots/build.sh clean`

### **Troubleshooting**
1. Health check: `./chatbots/build.sh check`
2. If API fails: Ensure `python api_server.py` is running
3. If React fails: Check port 3000 availability
4. Fresh start: `./chatbots/build.sh clean && ./chatbots/build.sh compose`

## Integration Points

### **With API Server**
- Health endpoint: `/health`
- JSON response formatting
- Port 8000 assumption

### **With Docker Infrastructure**
- Uses existing Dockerfiles
- Integrates with docker-compose.yml
- Consistent service naming

### **With Project Structure**
- Respects existing directory layout
- Uses project root context for Docker builds
- Maintains separation of concerns

## Performance Considerations

### **Build Optimization**
- Production builds are minified and optimized
- Build size reporting for monitoring
- Suggests appropriate deployment methods

### **Development Efficiency**
- Conditional dependency installation
- Fast health checks with timeouts
- Background service management

## Security Notes

### **Container Security**
- Uses `--rm` flag for automatic cleanup
- Minimal container exposure
- Host network isolation via `host.docker.internal`

### **Development Safety**
- Non-privileged container execution
- Graceful error handling prevents hanging processes
- Clean shutdown procedures

## Maintenance

### **Script Updates**
- Add new commands by extending the `case` statement in `main()`
- Follow existing logging patterns for consistency
- Update help text when adding features

### **Docker Updates**
- Update Dockerfile references if paths change
- Maintain environment variable consistency
- Test full stack integration after changes

## Future Enhancements

### **Potential Improvements**
1. **Build Caching**: Use `npm ci` for faster, reproducible builds
2. **SSL Support**: Add HTTPS configuration for production
3. **Environment Switching**: Support dev/staging/prod configs
4. **Log Management**: Add log rotation and filtering
5. **Test Integration**: Add Playwright test execution
6. **Auto-restart**: Monitor and auto-restart failed services

### **Advanced Features**
- Blue/green deployment support
- Load balancer integration
- Monitoring dashboard integration
- Backup and restore capabilities

## Troubleshooting Guide

### **Common Issues**

#### Script Permission Denied
```bash
chmod +x chatbots/build.sh
```

#### Node.js/npm Not Found
```bash
# Install Node.js via package manager
brew install node  # macOS
apt install nodejs npm  # Ubuntu
```

#### Docker Not Running
```bash
# Start Docker service
sudo systemctl start docker  # Linux
# Or start Docker Desktop
```

#### Port Already in Use
```bash
# Find and kill process using port
lsof -ti:3000 | xargs kill -9
lsof -ti:8000 | xargs kill -9
```

#### Build Failures
1. Clear npm cache: `npm cache clean --force`
2. Delete `node_modules`: `rm -rf react-chatbot/node_modules`
3. Fresh install: `npm install`

This script provides a **production-ready foundation** for React chatbot development and deployment workflows, with room for future enhancements based on specific deployment requirements.
