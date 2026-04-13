# Documentation Index

Quick navigation for committed documentation in this project.

**Quick Start By Role:**
- **New Developer**: Start with [README.md](../README.md) → [GETTING_STARTED.md](#getting-started--quick-reference) → [ARCHITECTURE.md](#system-architecture--development)
- **API Developer**: [API_SERVER.md](#api--integration) → [ARCHITECTURE.md](#system-architecture--development)
- **Feature Developer**: [DEVELOPMENT.md](#system-architecture--development) → [ARCHITECTURE.md](#system-architecture--development)
- **DevOps/Deployment**: [GETTING_STARTED.md](#getting-started--quick-reference) → [REACT_DEPLOYMENT.md](#deployment)

---

## 🚀 Recent Updates

**Infrastructure Status Analysis (Apr 12, 2026)**: Added comprehensive analysis of actual implementation status vs documentation claims. Verified that core monitoring, retry logic, and health checks are actively working in production, while advanced features (circuit breakers, tracing) are production-ready frameworks. See [INFRASTRUCTURE_IMPLEMENTATION_STATUS.md](INFRASTRUCTURE_IMPLEMENTATION_STATUS.md).

**Strands Core Agent (Apr 12, 2026)**: Added specialized Strands agent for documentation and programming assistance with 3-node architecture (TaskValidator → TaskRouter → SpecializedWorkers). Includes 9 tools across 2 skills for comprehensive code analysis and documentation management. See [STRANDS_CORE_AGENT.md](STRANDS_CORE_AGENT.md).

**Graph Agent Architecture (Mar 5, 2026)**: Migrated to 3-node graph-based `StrandsGraphRAGAgent` with pattern-matching security detection. All 77 tests passing. See [ARCHITECTURE.md](ARCHITECTURE.md) and [tests/README.md](../tests/README.md) for details.

**Test Suite Migration (Mar 5, 2026)**: Updated test suite to use new graph agent. 48% code coverage across 619/1303 statements. See [tests/README.md](../tests/README.md) for test statistics.

**Cache System Optimized (Mar 7, 2026)**: Semantic response caching provides <50ms cache hits vs 1-15s full generation. See [CACHING_STRATEGY.md](CACHING_STRATEGY.md).

---

## 📚 Committed Documentation Files

### System Architecture & Development
- **[IMPLEMENTATION_ARCHITECTURE.md](IMPLEMENTATION_ARCHITECTURE.md)** - Complete RAG system implementation documentation with infrastructure components
- **[INFRASTRUCTURE_IMPLEMENTATION_STATUS.md](INFRASTRUCTURE_IMPLEMENTATION_STATUS.md)** - Actual implementation status vs documentation claims
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** - Quick API reference and usage patterns for developers
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Three-tier system architecture (Cache → KB → Web Search) + complete component details
- **[QUERY_ROUTING.md](QUERY_ROUTING.md)** - Complete query routing paths, validation layers, and decision logic
- **[AWS_ARCHITECTURE.md](AWS_ARCHITECTURE.md)** - AWS deployment architectures (ECS/Fargate, Lambda + AgentCore)
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development guidelines and patterns
- **[STRANDS_CORE_AGENT.md](STRANDS_CORE_AGENT.md)** - Specialized agent for documentation and programming assistance
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

**Note**: This index documents only committed/staged documentation files in docs/ + README.md at root (14 total).
