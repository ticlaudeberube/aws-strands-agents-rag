# Docker Migration Guide

Migrate from milvus-standalone to the optimized Docker setup in the aws-strands-agents-rag project.

## Overview

**Before**: Using `../milvus-standalone` for Docker services  
**After**: Using `./docker/` for integrated optimized services

## Migration Steps

### Option 1: Full Migration (Recommended)

Complete migration to the new optimized Docker setup:

```bash
cd /Users/claude/Documents/workspace/aws-strands-agents-rag

# 1. Stop current milvus-standalone containers
cd ../milvus-standalone
docker-compose down
cd ../aws-strands-agents-rag

# 2. Backup volumes (optional, for data preservation)
mkdir -p backups
cp -r ../milvus-standalone/volumes backups/milvus_volumes_backup

# 3. Start new optimized services
cd docker
./optimize.sh --all

# 4. Verify everything is running
docker-compose ps
```

### Option 2: Quick Start (Data Loss)

Faster migration without data preservation:

```bash
cd /Users/claude/Documents/workspace/aws-strands-agents-rag

# Stop old services
cd ../milvus-standalone && docker-compose down && cd ../aws-strands-agents-rag

# Start new services
cd docker && ./optimize.sh --all
```

### Option 3: Manual Migration

For more control:

```bash
cd /Users/claude/Documents/workspace/aws-strands-agents-rag

# 1. Stop current containers
cd ../milvus-standalone
docker-compose down

# 2. Clean up Docker resources (optional)
docker system prune -f

# 3. Start new services
cd ../aws-strands-agents-rag/docker
docker-compose up -d

# 4. Verify services
docker-compose ps
sleep 30
docker-compose logs milvus | head -20
```

## Post-Migration Tasks

### 1. Verify Services

```bash
cd /Users/claude/Documents/workspace/aws-strands-agents-rag/docker

# Check all services are healthy
docker-compose ps
```

Expected output:
```
NAME                COMMAND                  SERVICE   STATUS
rag-etcd            "etcd -advertise-cli…"   etcd      Up (healthy)
rag-minio           "minio server /minio…"   minio     Up (healthy)
rag-milvus          "milvus run standalo…"   milvus    Up (healthy)
rag-api             "python api_server.py"   rag-api   Up (healthy)
```

### 2. Verify Collections

```bash
# Check if collections exist and are using correct name from .env
python scripts/verify_collection.py
```

### 3. Load Data (If Needed)

If collections don't exist or data was lost:

```bash
# Ensure Milvus is ready
sleep 30

# Load documentation
python document-loaders/load_milvus_docs_ollama.py
```

### 4. Test the System

```bash
# Quick setup check
python scripts/check_setup.py

# Test API health
curl http://localhost:8000/health

# Test interactive chat
python chatbots/interactive_chat.py
```

## Configuration

The new Docker setup reads configuration from two main sources:

### 1. `.env` File

Located at project root: `/Users/claude/Documents/workspace/aws-strands-agents-rag/.env`

Key variables:
- `MILVUS_HOST`: localhost or milvus (in Docker)
- `MILVUS_PORT`: 19530
- `OLLAMA_COLLECTION_NAME`: milvus_rag_collection (used by all services)
- `OLLAMA_HOST`: http://host.docker.internal:11434 (from Docker, connects to local Ollama)

### 2. Docker Environment

The services are configured in `docker-compose.yml`:
- Container names: `rag-etcd`, `rag-minio`, `rag-milvus`, `rag-api`
- Network: Custom bridge `rag-network` (172.28.0.0/16)
- Volumes: Named volumes for data persistence

## Port Mappings

**Old Setup:**
- Milvus gRPC: localhost:19530
- Milvus HTTP: localhost:9091
- MinIO Console: localhost:9001
- MinIO API: localhost:9000

**New Setup:** (Same ports)
- Milvus gRPC: localhost:19530
- Milvus HTTP: localhost:9091
- MinIO Console: localhost:9001
- MinIO API: localhost:9000
- RAG API: localhost:8000 (new)

## Troubleshooting

### Services Won't Start

```bash
cd docker

# Check logs
docker-compose logs -f milvus
docker-compose logs -f rag-api

# Try restarting
docker-compose restart

# Or full restart
docker-compose down && docker-compose up -d
```

### Out of Memory

```bash
# Check resource usage
docker stats

# Increase Docker Desktop resources:
# Docker Menu → Preferences → Resources → Increase Memory
```

### Ollama Connection Issues

The RAG API container connects to Ollama using `http://host.docker.internal:11434`.

```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# If not working, Ollama may not be running:
# macOS: Open Ollama app or run: ollama serve
```

### Collection Not Found

```bash
# Verify configured collection
grep OLLAMA_COLLECTION_NAME .env

# Check what collections exist
python scripts/verify_collection.py

# If none exist, load data
python document-loaders/load_milvus_docs_ollama.py
```

## Rollback (If Needed)

To revert to the old milvus-standalone setup:

```bash
# Stop new services
cd /Users/claude/Documents/workspace/aws-strands-agents-rag/docker
docker-compose down

# Start old services
cd ../milvus-standalone
docker-compose up -d
```

## Performance Improvements

The new setup includes:

✅ **Docker-level Optimizations**
- Memory limits prevent resource exhaustion
- tmpfs volumes for faster temporary file access
- Init process for proper signal handling
- Automatic health checks and recovery

✅ **Milvus Optimizations**
- 4 CPU cores allocated
- 8GB memory with proper limits
- 2GB query cache
- 50GB disk cache enabled
- 8 parallel index builders

✅ **Network Optimization**
- Custom bridge network for isolation
- Better container communication

✅ **Alpine Images**
- Smaller, faster image pulls
- Reduced memory footprint

## Comparison

| Aspect | Old | New |
|--------|-----|-----|
| Setup Location | `../milvus-standalone` | `./docker/` |
| Image Base | Full OS | Alpine (lighter) |
| Health Checks | Basic | Enhanced |
| Optimization Script | Generic | Integrated |
| Temp Storage | Disk | RAM (tmpfs) |
| Network | Default | Custom bridge |
| CPU Allocation | Less explicit | Defined per service |
| RAG API Container | Manual | Integrated |

## Support

For issues or questions:

1. Check logs: `docker-compose logs -f [service]`
2. Verify config: `python scripts/verify_collection.py`
3. Run diagnostics: `python scripts/check_setup.py`
4. See [Docker README](./docker/README.md) for detailed info
5. See [Collection Config Guide](./docs/COLLECTION_CONFIG.md) for data management
