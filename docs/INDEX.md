# Documentation Index

Quick navigation for committed documentation in this project.

**Quick Start By Role:**
- **New Developer**: Start with [README.md](../README.md) → [GETTING_STARTED.md](#getting-started--quick-reference) → [ARCHITECTURE.md](#system-architecture--development)
- **API Developer**: [API_SERVER.md](#api--integration) → [ARCHITECTURE.md](#system-architecture--development)
- **Feature Developer**: [DEVELOPMENT.md](#system-architecture--development) → [ARCHITECTURE.md](#system-architecture--development)
- **DevOps/Deployment**: [GETTING_STARTED.md](#getting-started--quick-reference) → [REACT_DEPLOYMENT.md](#deployment)

---

## 🚀 Recent Updates

**Three-Tier Architecture (Mar 1, 2026)**: Response caching, knowledge base retrieval, and opt-in web search. See [ARCHITECTURE.md](#system-architecture--development) for details.

**Cache Warmup Enabled (Mar 1, 2026)**: API server now automatically pre-loads Q&A pairs on startup for sub-50ms responses. See [CACHING_STRATEGY.md](#system-architecture--development) for implementation details.

---

## 📚 Committed Documentation Files

### System Architecture & Development
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Three-tier system architecture (Cache → KB → Web Search) + complete component details
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development guidelines and patterns
- **[CACHING_STRATEGY.md](CACHING_STRATEGY.md)** - Response cache architecture and configuration

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

**Note**: This index documents only committed/staged documentation files in docs/ + README.md at root (9 total).
