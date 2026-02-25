# RAG Application Docker Configuration

Optimized Docker deployment for the AWS Strands Agents RAG system with Milvus vector database, MinIO object storage, and etcd configuration management.

## Quick Start

### 1. Automatic Setup (Recommended)

Run the optimization script to configure Docker and start all services:

```bash
cd docker
chmod +x optimize.sh
./optimize.sh --all
```

### 2. Manual Startup

Start services without optimization:

```bash
cd docker
docker-compose up -d
```

## Docker Compose Services

### milvus (Vector Database)
- **Image**: `milvusdb/milvus:v2.6.0`
- **Port**: 19530 (gRPC), 9091 (HTTP/WebUI)
- **Resources**: 4 CPU cores, 8GB RAM
- **Features**:
  - 2GB query cache
  - 50GB disk cache enabled
  - 8 parallel index builders
  - Disk-based search enabled

### minio (Object Storage)
- **Image**: `minio/minio:RELEASE.2024-12-18T13-15-44Z`
- **Ports**: 9000 (API), 9001 (Console)
- **Resources**: 2 CPU cores, 2GB RAM
- **Console**: http://localhost:9001
- **Credentials**: minioadmin / minioadmin

### etcd (Configuration Storage)
- **Image**: `quay.io/coreos/etcd:v3.5.18`
- **Port**: 2379
- **Resources**: 1 CPU core, 1GB RAM
- **Features**:
  - Auto-compaction enabled
  - 4GB quota backend
  - High snapshot count (50000)

### rag-api (RAG Application)
- **Build**: From project Dockerfile
- **Port**: 8000
- **Resources**: 2 CPU cores, 2GB RAM
- **Health Check**: Every 30 seconds
- **Dependencies**: Requires milvus to be healthy

## Performance Optimizations Applied

### Docker-level Optimizations
- **Memory Limits**: Strict per-service limits to prevent resource exhaustion
- **CPU Allocation**: CPUs pinned to specific cores for isolation
- **tmpfs Volumes**: Temporary files use in-memory storage
- **Init Process**: `init: true` for proper signal handling
- **Healthchecks**: Automated service monitoring and recovery
- **Restart Policy**: Automatic restart on failure

### Milvus-specific Optimizations
```yaml
GOMAXPROCS: "4"           # Go runtime optimization
GOMEMLIMIT: "6GiB"        # Memory ceiling
Cache Size: 2GB           # Query node cache
Disk Cache: Enabled       # Disk-based searching
Parallel IndexBuilders: 8 # Concurrent index building
```

### System-level Optimizations
- File descriptor limits: 65536
- Memory locking enabled
- No memory swap for stable performance
- Custom bridge network for isolation

## macOS Docker Desktop Settings

For optimal performance, configure Docker Desktop:

1. **Open Docker Desktop Preferences** (⌘ + ,)
2. **Resources Tab**:
   - CPUs: 8+ cores
   - Memory: 16GB+
   - Swap: 2GB
   - Disk image size: 100GB+

3. **Features in development tab** (Experimental):
   - Enable **VirtioFS** (faster than osxfs)
   - Enable **Rosetta 2** (if using Apple Silicon)

4. **File Sharing**:
   - Ensure project directory is shared

## Linux System Optimization

Run the optimization script:

```bash
./optimize.sh --linux
```

This automatically configures:
- File descriptor limits (65536)
- vm.swappiness = 1
- vm.max_map_count = 262144
- Network optimizations

## Usage Commands

### Start All Services
```bash
docker-compose up -d
```

### Stop All Services
```bash
docker-compose down
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f milvus
docker-compose logs -f rag-api
docker-compose logs -f minio
```

### Monitor Resources
```bash
docker stats
```

### Check Service Health
```bash
docker-compose ps
```

### Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| Milvus gRPC | localhost:19530 | Vector database API |
| Milvus WebUI | http://localhost:9091/webui | Database management |
| MinIO API | localhost:9000 | Object storage API |
| MinIO Console | http://localhost:9001 | Storage management |
| RAG API | http://localhost:8000 | RAG application API |

### Health Checks
```bash
# RAG API health
curl http://localhost:8000/health

# Milvus health
curl http://localhost:9091/healthz

# MinIO health
curl http://localhost:9000/minio/health/live
```

## Environment Variables

The services use these key environment variables:

### For rag-api Service
- `MILVUS_HOST`: Vector database host (default: milvus)
- `MILVUS_PORT`: Vector database port (default: 19530)
- `OLLAMA_HOST`: Ollama server URL (currently http://host.docker.internal:11434)
- `LOG_LEVEL`: Logging level (default: INFO)

### For milvus Service
- `ETCD_ENDPOINTS`: etcd configuration store
- `MINIO_ADDRESS`: Object storage endpoint
- `MQ_TYPE`: Message queue type (woodpecker)

## Troubleshooting

### Services Won't Start
```bash
# Check Docker daemon
docker ps

# View initialization logs
docker-compose logs etcd
docker-compose logs minio
docker-compose logs milvus

# Restart services
docker-compose down && docker-compose up -d
```

### Out of Memory
```bash
# Check current resource usage
docker stats

# Increase Docker Desktop memory limits
# Docker Desktop Preferences → Resources → Memory
```

### Slow Performance
```bash
# Check CPU allocation
docker stats

# Monitor with extended information
docker stats --no-stream

# Check disk usage
docker system df

# Clean up unused resources
docker system prune -a
```

### Port Already in Use
```bash
# Find process using port (macOS/Linux)
lsof -i :19530  # Milvus
lsof -i :9001   # MinIO
lsof -i :8000   # RAG API

# Kill process if needed
kill -9 <PID>
```

## Performance Monitoring

### Real-time Statistics
```bash
docker stats
```

### Inspect Container Resources
```bash
docker inspect rag-milvus --format='{{json .HostConfig.Memory}}'
docker inspect rag-api --format='{{json .HostConfig.Memory}}'
```

### View Docker Disk Usage
```bash
docker system df
```

### Check Container CPU and Memory Limits
```bash
docker inspect rag-milvus | grep -A 5 "MemoryLimit\|CpuQuota"
```

## Deployment Checklist

- [ ] Docker Desktop is running
- [ ] Project directory is in Docker file sharing (macOS)
- [ ] Port 19530, 9000, 9001, 8000 are available
- [ ] At least 16GB RAM available to Docker
- [ ] At least 8 CPU cores allocated to Docker
- [ ] VirtioFS enabled on macOS (if available)
- [ ] Run `./optimize.sh --all` for initial setup
- [ ] Verify all services are healthy: `docker-compose ps`
- [ ] Test API health: `curl http://localhost:8000/health`

## Advanced Configuration

### Modify Service Resources
Edit `docker-compose.yml`:

```yaml
services:
  milvus:
    mem_limit: 16g          # Increase memory
    cpus: 8.0               # Increase CPUs
    cpuset_cpus: "0-7"      # Specific cores
```

### Enable Debug Logging
```yaml
services:
  milvus:
    environment:
      LOG_LEVEL: "debug"
```

### Custom Network
Currently uses custom bridge network `rag-network` (172.28.0.0/16) for isolation.

## References

- [Milvus Documentation](https://milvus.io/docs)
- [MinIO Documentation](https://docs.min.io/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Docker Performance Best Practices](https://docs.docker.com/build/building/best-practices/)
