
## Using dev_tools via Copilot Chat

You can use dev_tools capabilities interactively through GitHub Copilot Chat in VS Code:

- Simply ask Copilot Chat to perform a dev_tools action (e.g., "Analyze documentation in the docs/ folder using dev_tools").
- Copilot will import and run the relevant dev_tools function and return the result in the chat.

**Example prompts:**

- "Analyze documentation in docs/ using dev_tools."
- "Generate API documentation for dev_tools/strands_core_agent.py using dev_tools."
- "Assess project quality with dev_tools."

No code changes are required—just request the action in Copilot Chat and the result will be provided interactively.

# Strands Core Agent for Documentation and Programming Assistance

The Strands Core Agent is a specialized AI agent designed to assist with documentation management and programming tasks. It follows the established 3-node Strands architecture pattern for optimal performance and cost efficiency.

## Architecture

### 3-Node Design Pattern

```
User Request
    ↓
┌─────────────────────────────────────────────┐
│ 1. TASK VALIDATOR (Fast Model)              │ ← Validates request scope
│    - Determines task type                   │   - Early exit on invalid requests
│    - Validates scope boundaries             │   - Cost optimization
│    - Returns ValidationResult               │
└────────────┬────────────────────────────────┘
             ↓ (if valid)
┌─────────────────────────────────────────────┐
│ 2. TASK ROUTER (Fast Model)                 │ ← Routes to appropriate worker
│    - Routes to specialized workers          │   - Selects optimal execution path
│    - Considers task complexity              │   - Load balancing
└────────────┬────────────────────────────────┘
             ↓ (route to worker)
┌─────────────────────────────────────────────┐
│ 3. SPECIALIZED WORKERS (Powerful Model)     │ ← Execute specific tasks
│    a) DocumentationWorker + Tools           │   - analyze_files()
│    b) CodeAnalysisWorker + Tools            │   - generate_documentation()
│    c) ProjectAnalysisWorker + Tools         │   - assess_quality()
└────────────┬────────────────────────────────┘
             ↓
        Structured Results
```

### Cost Optimization Benefits

| Request Type | Path | Latency | Cost |
|-------------|------|---------|------|
| Invalid request | TaskValidator reject | ~100ms | ~1¢ |
| Out of scope | TaskValidator reject | ~120ms | ~1¢ |
| Valid documentation task | All 3 nodes + DocWorker | ~2000ms | ~8¢ |
| Valid code analysis | All 3 nodes + CodeWorker | ~2500ms | ~10¢ |

**Savings**: 80-90% cost reduction on invalid/out-of-scope requests

## Core Capabilities

### 1. Documentation Management

#### Skills Available
- **analyze_documentation**: Comprehensive doc analysis
- **generate_docs**: Auto-generate from source code
- **improve_docs**: Suggest specific improvements
- **validate_docs_structure**: Check organization

#### Use Cases
```python
# Analyze existing documentation
result = await agent.process_request(
    "Analyze documentation in docs/ directory for completeness"
)

# Generate API documentation
result = await agent.process_request(
    "Generate API documentation for dev_tools/strands_core_agent.py"
)
```

### 2. Programming Assistance

#### Skills Available
- **analyze_code_quality**: Quality and complexity assessment
- **detect_patterns**: Design pattern identification
- **assess_project_quality**: Project-wide evaluation
- **review_code_structure**: Organization analysis
- **validate_best_practices**: Standards compliance

#### Use Cases
```python
# Analyze code quality
result = await agent.process_request(
    "Review code quality in src/agents/ and suggest improvements"
)

# Detect architectural patterns
result = await agent.process_request(
    "Analyze the codebase for design patterns and architecture"
)
```

### 3. Project Analysis

#### Comprehensive Assessment
- Structure organization
- Code quality metrics
- Documentation coverage
- Best practices adherence
- Architecture analysis

## Tool Reference

### Documentation Tools

#### `analyze_files`
**Purpose**: Analyze files and directories for documentation
**Parameters**:
- `path` (string): Directory or file path
- `file_pattern` (string, optional): Filter pattern (e.g., "*.md")
- `recursive` (boolean, default: true): Search subdirectories

**Returns**:
```json
{
  "files_found": 15,
  "files_analyzed": 12,
  "file_details": [...],
  "issues": [...],
  "timestamp": 1640995200.0
}
```

#### `generate_documentation`
**Purpose**: Generate documentation from source code
**Parameters**:
- `source_path` (string): Path to source file/directory
- `doc_type` (string): "api", "readme", "guide", "reference"
- `output_format` (string): "markdown", "rst", "html"

**Returns**:
```json
{
  "content": "# Generated Documentation...",
  "type": "api",
  "format": "markdown",
  "source": "src/agents/core_agent.py"
}
```

### Programming Tools

#### `analyze_code_quality`
**Purpose**: Comprehensive code quality analysis
**Parameters**:
- `file_path` (string): Path to code file
- `analysis_type` (string): "basic", "comprehensive", "security"

**Returns**:
```json
{
  "analysis": {
    "file": "api_server.py",
    "language": "python",
    "lines_of_code": 850,
    "complexity_indicators": {...},
    "documentation_coverage": {...},
    "potential_issues": [...]
  }
}
```

#### `detect_patterns`
**Purpose**: Identify design patterns and architecture
**Parameters**:
- `directory_path` (string): Directory to analyze
- `pattern_types` (array, optional): Specific patterns to look for

**Returns**:
```json
{
  "patterns_detected": [
    "Factory pattern detected in agent_factory.py",
    "Singleton pattern detected in config.py"
  ],
  "architectural_insights": [
    "Layered architecture (src/ directory)",
    "Agent-based architecture"
  ]
}
```

#### `assess_quality`
**Purpose**: Overall project quality assessment
**Parameters**:
- `project_path` (string): Root project path
- `focus_areas` (array, optional): Specific areas to focus on

**Returns**:
```json
{
  "overall_quality": 0.75,
  "area_scores": {
    "structure": 0.8,
    "documentation": 0.6,
    "testing": 0.7,
    "code_quality": 0.9
  },
  "recommendations": [...]
}
```

## MCP Integration

### Core Agent MCP Server

```python
from src.mcp.core_agent_server import CoreAgentMCPServer

# Initialize server
server = CoreAgentMCPServer(settings)

# Get available tools
tools = server.get_tools()

# Invoke tools via MCP
result = await server.invoke_tool(
    "analyze_code_quality",
    {"file_path": "api_server.py", "analysis_type": "comprehensive"}
)
```

### Integrated Server (RAG + Core)

```python
from dev_tools.mcp_server import IntegratedMCPServer

# Combined capabilities
integrated = IntegratedMCPServer(settings)

# Access both RAG and Core tools
all_tools = integrated.get_all_tools()
status = integrated.get_server_status()
```

## Configuration

### Environment Variables

```bash
# Core agent settings (uses existing Ollama settings)
OLLAMA_MODEL=qwen2.5:0.5b          # Fast model for validation/routing
OLLAMA_HOST=http://localhost:11434  # Ollama server
MAX_TOKENS=256                      # Token limit per response

# Optional: Specific models for different workers
CORE_AGENT_VALIDATION_MODEL=qwen2.5:0.5b    # Fast validation
CORE_AGENT_WORKER_MODEL=llama3.1:8b         # Powerful workers
```

### Settings Integration

The Core Agent reuses existing settings from your project:

```python
from src.config.settings import Settings

settings = Settings()  # Automatically loads from .env

# Uses these existing settings:
# - settings.ollama_model
# - settings.ollama_host
# - settings.max_tokens
# - All other Ollama configuration
```

## Usage Examples

### 1. Basic Documentation Analysis

```python
import asyncio
from src.config import Settings
from src.agents.strands_core_agent import StrandsCoreAgent

async def analyze_docs():
    settings = Settings()
    agent = StrandsCoreAgent(settings)

    result = await agent.process_request(
        "Analyze the documentation in docs/ and suggest improvements"
    )

    print(f"Status: {result['status']}")
    print(f"Processing time: {result['processing_time']:.2f}s")

asyncio.run(analyze_docs())
```

### 2. Code Quality Review

```python
async def review_code():
    agent = StrandsCoreAgent(Settings())

    result = await agent.process_request(
        "Review code quality in src/agents/strands_graph_agent.py"
    )

    if result['status'] == 'completed':
        analysis = result['analysis_result']
        print("Code review completed successfully")

asyncio.run(review_code())
```

### 3. Project Assessment

```python
async def assess_project():
    agent = StrandsCoreAgent(Settings())

    result = await agent.process_request(
        "Provide comprehensive analysis of project structure and quality"
    )

    if result['status'] == 'completed':
        project_analysis = result['project_analysis']
        print("Project assessment completed")

asyncio.run(assess_project())
```

### 4. Direct Tool Access

```python
# Use tools directly without the routing layer
agent = StrandsCoreAgent(Settings())

# Analyze files
file_result = agent.analyze_files("src/", "*.py", True)

# Generate documentation
doc_result = agent.generate_documentation(
    "api_server.py", "api", "markdown"
)

# Assess quality
quality_result = agent.assess_quality(".", ["structure", "testing"])
```

## Error Handling

### Task Validation Failures

```python
result = await agent.process_request("What's the weather?")

if result['status'] == 'rejected':
    print(f"Request rejected: {result['reason']}")
    print(f"Task type identified: {result['task_type']}")
```

### Tool Execution Errors

```python
result = await server.invoke_tool("analyze_files", {"path": "/nonexistent"})

if result.get('error'):
    print(f"Tool error: {result['error']}")
```

## Performance Considerations

### Model Selection

- **Validation/Routing**: Use fast models (qwen2.5:0.5b) for ~100ms responses
- **Workers**: Use powerful models (llama3.1:8b) for quality analysis

### Caching Strategy

- File analysis results cached for 1 hour
- Documentation generation cached by source file hash
- Pattern detection cached by directory structure

### Scalability

- Each agent node can be scaled independently
- MCP server supports concurrent tool invocations
- Tool execution is stateless and parallelizable

## Integration with Existing System

### Skillset Addition

The Core Agent integrates seamlessly with your existing RAG system:

```python
# Existing skills remain available
from src.agents.skills import RetreivalSkill, AnswerGenerationSkill

# Add new skills
from src.agents.skills import DocumentationSkill, ProgrammingSkill

# Combined in IntegratedMCPServer
integrated = IntegratedMCPServer(settings)
```

### Tool Registry Integration

```python
from src.tools.tool_registry import get_registry

registry = get_registry()

# Core agent tools automatically registered
DocumentationSkill.register_tools(registry, agent)
ProgrammingSkill.register_tools(registry, agent)
```

## Monitoring and Observability

### Execution Tracing

```python
result = await agent.process_request(request)

print(f"Processing time: {result['processing_time']:.2f}s")
print(f"Task type: {result['task_type']}")
print(f"Execution path: validation → routing → {result['task_type']}")
```

### Tool Usage Metrics

```python
# MCP server provides usage statistics
server = CoreAgentMCPServer(settings)
summary = server.get_skill_summary()

print(f"Total tools: {summary['total_tools']}")
print(f"Skills registered: {summary['total_skills']}")
```

## Future Extensions

### Additional Skills

- **Testing Skill**: Generate and analyze test cases
- **Security Skill**: Security-focused code analysis
- **Performance Skill**: Performance optimization suggestions
- **Migration Skill**: Code migration assistance

### Enhanced Capabilities

- Multi-language support (TypeScript, Java, Go)
- Integration with external tools (ESLint, Pylint)
- Custom documentation templates
- AI-powered refactoring suggestions

---

## Quick Start Checklist

1. ✅ Ensure Ollama is running (`ollama serve`)
2. ✅ Install dependencies (`pip install -r requirements.txt`)
3. ✅ Configure `.env` file with Ollama settings
4. ✅ Import and initialize: `StrandsCoreAgent(Settings())`
5. ✅ Test with: `await agent.process_request("Analyze docs in docs/")`

**Ready to enhance your development workflow with AI-powered documentation and code assistance!**
