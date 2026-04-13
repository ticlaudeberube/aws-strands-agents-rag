---
description: "Quick generator for Strands Agent boilerplate code, 3-node patterns, @tool decorators, and MCP integration. Use for: create agent template, generate tool function, add MCP tool, implement validation pattern, scaffold agent architecture."
name: "Strands Generator"
---

Generate boilerplate code for Strands Agent framework development following this project's established patterns.

## Quick Start Usage

In VS Code Copilot chat:
1. Type `/strands-generator`
2. Add parameters: `task_type:agent agent_name:MyAgent`
3. Get instant boilerplate code ready to use

## Task Types

### `agent` - Complete 3-Node Architecture
Generates full agent with TopicChecker → SecurityChecker → Worker pattern
```
/strands-generator task_type:agent agent_name:DocumentAnalyzer model_type:fast
```

### `tool` - @tool Decorator Functions
Creates tool functions with proper typing and MCP integration
```
/strands-generator task_type:tool tool_name:search_documents
```

### `validation` - ValidationResult Models
Generates Pydantic models for routing decisions
```
/strands-generator task_type:validation
```

### `mcp` - MCP Server Integration
Creates MCP server tool registration boilerplate
```
/strands-generator task_type:mcp tool_name:analyze_code
```

### `routing` - Conditional Logic
Generates routing patterns with early exit optimization
```
/strands-generator task_type:routing
```

## Parameters Reference

| Parameter | Required | Values | Description |
|-----------|----------|--------|--------------|
| `task_type` | ✅ | agent, tool, validation, mcp, routing | Type of code to generate |
| `agent_name` | For agent | Any string | Name for the agent class |
| `tool_name` | For tool/mcp | snake_case | Function name for tools |
| `model_type` | For agent | fast, powerful | Model tier (fast=validation, powerful=work) |

## Real Usage Examples

### Create a New RAG Agent
```
/strands-generator task_type:agent agent_name:KnowledgeAgent model_type:powerful
```
Generates: Complete 3-node agent with search_knowledge_base and generate_response tools

### Add a Vector Search Tool
```
/strands-generator task_type:tool tool_name:vector_search
```
Generates: @tool decorated function with proper typing and error handling

### Build MCP Integration
```
/strands-generator task_type:mcp tool_name:code_analyzer
```
Generates: MCP server registration with schema and handlers

## Output

Returns ready-to-use code following project patterns with:
- Proper imports and type hints
- Established naming conventions
- Integration with existing MCP/RAG infrastructure
- Performance and cost optimization comments
