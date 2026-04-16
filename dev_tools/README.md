# Development Tools

This directory contains development utilities and helper tools that support the development process but are not part of the production system.

## Quick Overview

**🎯 Purpose**: Specialized AI agents for code analysis, documentation management, and project assessment - beyond what standard GitHub Copilot provides.

**📋 Key Documents**:
- **[AGENT_OVERVIEW.md](AGENT_OVERVIEW.md)** - Complete guide: purpose, usage, and benefits over standard Copilot
- **[DOCUMENTATION.md](DOCUMENTATION.md)** - Technical reference and detailed API documentation
- **[README.md](README.md)** - This file: architecture and integration guide

## Contents

### Core Components

#### StrandsCoreAgent (`strands_core_agent.py`)
A specialized Strands agent for documentation and programming assistance. This agent is designed for development workflows, not production RAG operations.

**Capabilities:**
- Documentation analysis, generation, and improvement  
- Code analysis, review, and suggestions
- Project structure analysis and recommendations
- Integration with existing codebase patterns

**Architecture:**
- 3-node pattern: TaskValidator → TaskRouter → SpecializedWorkers
- Multiple specialized tools for analysis and generation
- Follows Strands agent framework patterns

#### Skills (`skills/`)
Specialized skills used by the StrandsCoreAgent:
- **DocumentationSkill**: Documentation analysis, generation, structure assessment
- **ProgrammingSkill**: Code review, complexity analysis, pattern detection

#### MCP Server (`mcp_server.py`)
Model Context Protocol server that exposes StrandsCoreAgent tools to external systems:
- **CoreAgentMCPServer**: Basic MCP interface for development tools
- **IntegratedMCPServer**: Combined interface with both RAG and development tools

#### Demo (`demo.py`)  
Example usage patterns and integration demonstrations for the StrandsCoreAgent.

#### Documentation (`DOCUMENTATION.md`)
Comprehensive documentation for the StrandsCoreAgent architecture, tools, and usage patterns.

## Usage

### **🚀 Run the Demo**
```bash
# Complete demonstration of all capabilities
python dev_tools/demo.py
```

### **🔧 Direct Python Usage**
```python
from dev_tools import StrandsCoreAgent
from src.config import Settings

settings = Settings()
agent = StrandsCoreAgent(settings)

# Analyze documentation
docs = await agent.analyze_documentation("docs/")

# Review code 
review = await agent.review_code("src/agents/")

# Generate documentation
docs = await agent.generate_documentation("api_server.py")
```

## Integration

### With Production System
```python
# Production RAG (user queries about Milvus/databases)
from src.agents import StrandsGraphRAGAgent

# Development utilities (code/docs analysis) 
from dev_tools import StrandsCoreAgent
```

### With MCP Protocol
```python
# Production RAG MCP (user query handling)
from src.mcp import RAGAgentMCPServer
rag_server = RAGAgentMCPServer(settings)

# Development tools MCP (code/docs analysis)
from dev_tools.mcp_server import CoreAgentMCPServer, IntegratedMCPServer

# Development tools only
dev_server = CoreAgentMCPServer(settings)

# Combined RAG + development tools
integrated_server = IntegratedMCPServer(settings)
```

## Architectural Separation

**Production System** (`src/`):
- **StrandsGraphRAGAgent**: Handles user queries about Milvus/vector databases
- **Production Skills**: Retrieval, answer generation, knowledge base operations
- **Production MCP**: `src/mcp/mcp_server.py` - Exposes RAG capabilities (RAGAgentMCPServer)

**Development Tools** (`dev_tools/`):
- **StrandsCoreAgent**: Code and documentation development assistance
- **Development Skills**: Documentation and programming analysis
- **Development MCP**: `dev_tools/mcp_server.py` - Exposes development tools (CoreAgentMCPServer)

## Purpose

The dev_tools directory maintains clear architectural boundaries while providing comprehensive development assistance. All components work together to support code development, documentation generation, and analysis workflows separate from production RAG operations.