# Documentation Index

Quick navigation for committed documentation in this project.

**Quick Start By Role:**
- **New Developer**: Start with [README.md](../README.md) → [GETTING_STARTED.md](#getting-started--quick-reference) → [ARCHITECTURE.md](#system-architecture--development)
- **API Developer**: [API_SERVER.md](#api--integration) → [ARCHITECTURE.md](#system-architecture--development)
- **Feature Developer**: [DEVELOPMENT.md](#system-architecture--development) → [ARCHITECTURE.md](#system-architecture--development)
- **DevOps/Deployment**: [GETTING_STARTED.md](#getting-started--quick-reference) → [REACT_DEPLOYMENT.md](#deployment)

---

## 🚀 Recent Updates

**Graph Agent Architecture (Mar 5, 2026)**: Migrated to 3-node graph-based `StrandsGraphRAGAgent` with pattern-matching security detection. All 77 tests passing. See [ARCHITECTURE.md](ARCHITECTURE.md) and [tests/README.md](../tests/README.md) for details.

**Test Suite Migration (Mar 5, 2026)**: Updated test suite to use new graph agent. 48% code coverage across 619/1303 statements. See [tests/README.md](../tests/README.md) for test statistics.

**Cache System Optimized (Mar 7, 2026)**: Semantic response caching provides <50ms cache hits vs 1-15s full generation. See [CACHING_STRATEGY.md](CACHING_STRATEGY.md).

---

## 📚 Committed Documentation Files

### System Architecture & Development
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Three-tier system architecture (Cache → KB → Web Search) + complete component details
- **[AWS_ARCHITECTURE.md](AWS_ARCHITECTURE.md)** - AWS deployment architectures (ECS/Fargate, Lambda + AgentCore)
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development guidelines and patterns
- **[CACHING_STRATEGY.md](CACHING_STRATEGY.md)** - Current semantic response cache implementation (single-layer Milvus)
- **[CACHING_STRATEGY_IMPROVEMENTS.md](CACHING_STRATEGY_IMPROVEMENTS.md)** - 11 caching improvements for container-based deployment
- **[AGENTCORE_CACHING_STRATEGY.md](AGENTCORE_CACHING_STRATEGY.md)** - Caching strategy for serverless AgentCore deployment

### Getting Started & Quick Reference
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Installation and setup guide
- **[STRANDS_QUICK_REFERENCE.md](STRANDS_QUICK_REFERENCE.md)** - Quick reference for common tasks

### API & Integration
- **[API_SERVER.md](API_SERVER.md)** - REST API and MCP server endpoints

### Performance
- **[MODEL_PERFORMANCE_COMPARISON.md](MODEL_PERFORMANCE_COMPARISON.md)** - Model benchmarking and performance analysis

### Deployment
- **[REACT_DEPLOYMENT.md](REACT_DEPLOYMENT.md)** - React chatbot deployment (Local, Docker, Serverless)

---

**Note**: This index documents only committed/staged documentation files in docs/ + README.md at root (13 total).
