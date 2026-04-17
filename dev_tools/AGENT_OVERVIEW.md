# StrandsCoreAgent: Advanced Development Assistant

## Quick Start

### Prerequisites
1. **Ollama**: Ensure Ollama is running (`ollama serve`)
2. **Dependencies**: Install requirements (`pip install -r requirements.txt`)
3. **Environment**: Configure `.env` file with Ollama settings
4. **Python**: Python 3.8+ with async support

### Basic Usage (30 seconds to start)

```python
from dev_tools import StrandsCoreAgent
from src.config import Settings

# 1. Initialize agent
settings = Settings()
agent = StrandsCoreAgent(settings)

# 2. Analyze documentation quality
result = await agent.process_request(
    "Analyze the documentation in docs/ and suggest improvements"
)

# 3. Review code quality
code_review = await agent.process_request(
    "Review code quality in src/agents/ and provide recommendations"
)

# 4. Generate missing documentation
docs = await agent.process_request(
    "Generate API documentation for api_server.py"
)

print(f"✅ Documentation quality: {result.get('quality_score', 'N/A')}")
print(f"✅ Code issues found: {len(code_review.get('issues', []))}")
```

### Real-World Example: Project Health Check

```python
async def project_health_check():
    """Complete project assessment in one function."""

    agent = StrandsCoreAgent(Settings())

    # Comprehensive analysis
    tasks = [
        "Analyze documentation quality and completeness in docs/",
        "Review code quality and complexity in src/",
        "Assess project structure and organization",
        "Generate missing API documentation for main modules"
    ]

    results = {}
    for task in tasks:
        results[task] = await agent.process_request(task)

    # Display summary
    print("🔍 Project Health Report:")
    for task, result in results.items():
        status = "✅" if result.get('status') == 'completed' else "❌"
        print(f"{status} {task}")

    return results

# Run it
health_report = await project_health_check()
```

## Overview

The `StrandsCoreAgent` is a specialized AI agent built on the Strands framework that provides comprehensive development assistance beyond standard GitHub Copilot capabilities. Unlike traditional coding assistants that focus on code completion and simple suggestions, StrandsCoreAgent offers deep analytical, architectural, and documentation capabilities for entire projects.

## Core Purpose

### Primary Objectives
1. **Comprehensive Code Analysis**: Deep quality assessment, complexity analysis, and architectural review
2. **Intelligent Documentation Management**: Analysis, generation, and improvement of project documentation
3. **Project-Level Insights**: Holistic assessment of codebase structure, patterns, and best practices
4. **Development Workflow Enhancement**: Structured, task-specific assistance with measurable outcomes

### Target Use Cases
- **Documentation Debt Remediation**: Systematic analysis and improvement of project docs
- **Code Quality Audits**: Comprehensive assessment of existing codebases
- **Architecture Reviews**: Pattern detection and structural analysis
- **Project Onboarding**: Generate missing documentation and assess project health
- **Development Standards Enforcement**: Validate adherence to best practices

## Architecture: 3-Node Strands Pattern

```
User Request
     ↓
┌─────────────────────────────────────────────┐
│ 1. TASK VALIDATOR (Fast Model)             │ ← Validates scope & intent
│    - Determines task type and feasibility   │   - Documentation vs code analysis
│    - Routes to appropriate worker           │   - Rejects invalid requests
│    - Early validation and scope checking    │
└────────────┬────────────────────────────────┘
             ↓ (if valid)
┌─────────────────────────────────────────────┐
│ 2. TASK ROUTER (Fast Model)                │ ← Routes to specialist
│    - Documentation → DocumentationWorker    │   - Task-specific routing
│    - Code Analysis → CodeAnalysisWorker     │   - Optimal tool selection
│    - Generation → ContentGenerationWorker   │
└────────────┬────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────┐
│ 3. SPECIALIZED WORKERS (Powerful Model)    │ ← Execute with tools
│    a) DocumentationWorker + 6 tools        │   - analyze_files()
│    b) CodeAnalysisWorker + 6 tools         │   - generate_documentation()
│    c) ProjectAnalysisWorker + 6 tools      │   - assess_quality()
└────────────┬────────────────────────────────┘
             ↓
    Structured, Actionable Results
```

### Benefits of 3-Node Architecture
- **Early Validation**: Rejects invalid requests without expensive processing
- **Specialized Excellence**: Each worker optimized for specific task types
- **Cost Efficiency**: Fast models for routing, powerful models only when needed
- **Structured Outputs**: Consistent, parseable results with confidence scores

## Core Capabilities

### 1. Documentation Management

#### Advanced Documentation Analysis
```python
# Comprehensive documentation audit
analysis = await agent.analyze_documentation("docs/")
# Returns: quality scores, missing sections, improvement recommendations
```

**Capabilities:**
- **Quality Assessment**: Completeness, accuracy, clarity scoring
- **Structure Validation**: Organization and hierarchy analysis
- **Coverage Analysis**: Documentation-to-code ratio assessment
- **Consistency Checking**: Style and format validation across files
- **Gap Detection**: Identify missing documentation sections

#### Intelligent Documentation Generation
```python
# Generate API docs from source code
docs = await agent.generate_documentation("src/agents/", doc_type="api")
# Returns: Structured markdown with extracted classes, functions, docstrings
```

**Capabilities:**
- **API Documentation**: Extract classes, methods, and signatures
- **README Generation**: Project overview and usage guides
- **Architecture Docs**: High-level system design documentation
- **Code Comments**: Inline documentation suggestions

### 2. Programming Assistance

#### Deep Code Quality Analysis
```python
# Comprehensive code quality assessment
review = await agent.review_code("src/agents/strands_graph_agent.py")
# Returns: complexity scores, issues, refactoring suggestions
```

**Capabilities:**
- **Complexity Analysis**: Cyclomatic complexity, nesting depth, function size
- **Pattern Detection**: Design patterns, anti-patterns, architectural issues
- **Best Practices Validation**: PEP compliance, naming conventions, structure
- **Technical Debt Assessment**: Code smells, maintainability issues
- **Security Analysis**: Basic security pattern validation

#### Project-Wide Architecture Analysis
```python
# Holistic project assessment
assessment = await agent.process_request(
    "Provide comprehensive analysis of project structure and quality"
)
```

**Capabilities:**
- **Architectural Patterns**: MVC, Factory, Observer pattern detection
- **Dependency Analysis**: Module coupling and cohesion assessment
- **Code Organization**: Directory structure and file organization review
- **Testing Coverage**: Test-to-code ratio and coverage analysis

### 3. Structured Output Models

All results use typed Pydantic models for consistent, parseable outputs:

```python
class DocumentationAnalysis(BaseModel):
    files_analyzed: int
    issues_found: List[Dict]
    recommendations: List[str]
    quality_score: float  # 0.0 - 1.0
    missing_docs: List[str]

class CodeAnalysis(BaseModel):
    files_analyzed: int
    complexity_score: float  # 0.0 - 1.0
    issues: List[Dict]
    suggestions: List[str]
    patterns_detected: List[str]
```

## Usage Patterns

### 1. Basic Usage - Natural Language Interface

```python
from dev_tools import StrandsCoreAgent
from src.config import Settings

# Initialize agent
settings = Settings()
agent = StrandsCoreAgent(settings)

# Natural language requests (recommended)
result = await agent.process_request(
    "Analyze the documentation in docs/ and suggest improvements"
)

# Structured output with quality scores and recommendations
print(f"Documentation quality: {result['quality_score']}")
print(f"Recommendations: {result['recommendations']}")
```

### 2. Direct Tool Access - Programmatic Interface

```python
# Direct tool access for integration workflows
agent = StrandsCoreAgent(settings)

# Analyze specific files
file_analysis = agent.file_analysis_tool(
    path="src/agents/",
    file_pattern="*.py",
    recursive=True
)

# Generate documentation
docs = agent.documentation_tool(
    source_path="api_server.py",
    doc_type="api",
    output_format="markdown"
)

# Assess project quality
quality = agent.quality_tool(
    project_path=".",
    focus_areas=["structure", "testing", "documentation"]
)
```

### 3. Batch Processing - Multiple Files/Directories

```python
# Process multiple directories systematically
directories = ["src/agents/", "src/tools/", "src/config/"]

for directory in directories:
    analysis = await agent.process_request(
        f"Analyze code quality in {directory} and provide improvement recommendations"
    )

    # Process structured results
    if analysis['status'] == 'completed':
        print(f"Directory: {directory}")
        print(f"Quality Score: {analysis['quality_score']}")
        print(f"Issues: {len(analysis['issues'])}")
```

### 4. Integration with Development Workflows

```python
# Pre-commit hook integration
async def validate_changes(changed_files: List[str]) -> bool:
    """Validate code quality before commit."""

    agent = StrandsCoreAgent(Settings())

    for file_path in changed_files:
        if file_path.endswith('.py'):
            analysis = await agent.review_code(file_path)

            # Block commit if critical issues found
            if analysis.complexity_score < 0.3:
                print(f"❌ Code quality too low in {file_path}")
                return False

    return True

# CI/CD pipeline integration
async def generate_docs_pipeline():
    """Generate documentation as part of CI pipeline."""

    agent = StrandsCoreAgent(Settings())

    # Generate API docs for all Python files
    docs = await agent.generate_documentation("src/", doc_type="api")

    # Write to docs directory
    with open("docs/api.md", "w") as f:
        f.write(docs.content)
```

## Benefits Over Standard GitHub Copilot

### 1. **Scope and Depth of Analysis**

| Feature | GitHub Copilot | **Strands Expert Agent** | **StrandsCoreAgent** |
|---------|---------------|---------------------------|----------------------|
| **Code Suggestions** | ✅ Excellent context-aware completions | ✅ **Strands-specific guidance** | ⚠️ Limited - not primary focus |
| **Quality Analysis** | ⚠️ Basic syntax checking | ⚠️ Conceptual advice only | ✅ **Deep quality with scores** |
| **Documentation** | ⚠️ Simple comment generation | ✅ **Development guidance** | ✅ **Comprehensive docs analysis** |
| **Project Assessment** | ❌ No project-level insights | ✅ **Architecture recommendations** | ✅ **Quantified project evaluation** |
| **Agent Development** | ❌ No Strands knowledge | ✅ **Expert Strands patterns** | ⚠️ Analysis focus, not creation |
| **Real-time Execution** | ❌ No task execution | ❌ Guidance only | ✅ **Automated analysis & generation** |

### 2. **Structured, Actionable Output**

**GitHub Copilot:**
```
# Provides suggestions in natural language comments
# Limited to inline completions and chat responses
```

**StrandsCoreAgent:**
```python
# Provides structured, parseable results
DocumentationAnalysis(
    files_analyzed=15,
    quality_score=0.72,
    issues_found=[
        {"file": "README.md", "issue": "Missing installation section"},
        {"file": "api.md", "issue": "Outdated endpoint documentation"}
    ],
    recommendations=[
        "Add API authentication examples",
        "Include troubleshooting section"
    ]
)
```

### 3. **Task Specialization**

**GitHub Copilot:** General-purpose coding assistant
- Best for: Code completion, simple explanations, basic refactoring
- Limitations: No specialized domain expertise, shallow analysis

**StrandsCoreAgent:** Specialized development consultant
- **Documentation Expert**: Comprehensive docs management and generation
- **Code Quality Auditor**: Deep analysis with quantified metrics
- **Architecture Advisor**: Pattern detection and structural recommendations
- **Project Consultant**: Holistic assessment with actionable insights

### 4. **Integration Capabilities**

**GitHub Copilot:**
- IDE integration only
- Limited programmatic access
- No pipeline integration

**StrandsCoreAgent:**
- **MCP Server**: Model Context Protocol for external tool integration
- **API Interface**: RESTful endpoints for CI/CD integration
- **Programmatic Access**: Direct Python API for custom workflows
- **Batch Processing**: Handle multiple files/directories systematically

## Integration with Strands Expert Agent

### **🤝 Complementary Development Workflow**

This project includes **two specialized agents** that work together for comprehensive Strands development:

#### **1. Strands Expert Agent** (`.github/agents/strands-expert.agent.md`)
- **Purpose**: VS Code Copilot agent for **development guidance and assistance**
- **Usage**: `@strands-expert` in VS Code Copilot Chat
- **Specialization**: Strands framework patterns, architecture advice, debugging help

#### **2. StrandsCoreAgent** (`dev_tools/strands_core_agent.py`)
- **Purpose**: Executable Strands agent for **automated analysis and generation**
- **Usage**: Direct Python API or MCP server integration
- **Specialization**: Code quality assessment, documentation generation, project analysis

### **🔄 Combined Development Pattern**

```python
# Step 1: Get expert guidance during development
# In VS Code Chat: "@strands-expert How should I structure a 3-node agent?"
# Expert provides patterns and recommendations

# Step 2: Implement your agent following expert guidance
class MyStrandsAgent:
    def __init__(self, settings):
        # Follow patterns suggested by @strands-expert
        pass

# Step 3: Use StrandsCoreAgent to analyze and improve your implementation
from dev_tools import StrandsCoreAgent

agent = StrandsCoreAgent(Settings())
analysis = await agent.process_request(
    "Analyze the code quality in my_strands_agent.py and suggest improvements"
)

# Step 4: Apply improvements and repeat
print(f"Code quality score: {analysis['complexity_score']}")
print(f"Improvements needed: {analysis['suggestions']}")
```

### **🎯 Workflow Benefits**

| Development Phase | **Strands Expert Agent** | **StrandsCoreAgent** |
|---|---|---|
| **Planning** | ✅ Architecture guidance, pattern recommendations | ❌ |
| **Implementation** | ✅ Real-time coding assistance, debugging help | ❌ |
| **Code Review** | ✅ Expert feedback on Strands patterns | ✅ **Automated quality analysis** |
| **Documentation** | ✅ Writing guidance and structure advice | ✅ **Automated generation & analysis** |
| **Optimization** | ✅ Performance and cost optimization guidance | ✅ **Quantified complexity assessment** |
| **CI/CD Integration** | ❌ | ✅ **Programmatic quality gates** |

### **📋 Example Combined Usage**

```bash
# 1. Get expert guidance (VS Code Chat)
"@strands-expert I need a document classifier agent with cost optimization"

# 2. Implement following expert recommendations
# (Code development with @strands-expert assistance)

# 3. Automated analysis and validation
python -c "
from dev_tools import StrandsCoreAgent
agent = StrandsCoreAgent(Settings())

# Validate implementation
analysis = await agent.process_request(
    'Analyze my document_classifier.py for Strands best practices'
)

# Generate missing documentation
docs = await agent.process_request(
    'Generate API documentation for my agent implementation'
)

print('Implementation validated and documented automatically!')
"
```

### **🚀 Why This Combination is Powerful**

1. **Expert Guidance + Automated Validation**: Get human-like expertise during development, automated validation afterward
2. **Interactive + Batch Processing**: Chat-based assistance for questions, automated analysis for large codebases
3. **Development + Operations**: Expert patterns for building agents, automated tools for maintaining quality
4. **Learning + Enforcement**: Learn best practices from expert, enforce standards with automated analysis

## Universal Agent Compatibility

### **🔌 Model Context Protocol (MCP) Standard**

StrandsCoreAgent is built on the **Model Context Protocol**, making it compatible with **any MCP-compatible agent system**, not just the Strands Expert Agent.

#### **📋 Supported Agent Types**

| **Agent Type** | **Integration Method** | **Tools Available** |
|---|---|---|
| **Strands Expert Agent** | VS Code Copilot Chat (`@strands-expert`) | All dev tools + guidance |
| **Claude MCP** | MCP client connection | All dev tools via protocol |
| **GPT with MCP** | MCP client connection | All dev tools via protocol |
| **Custom Strands Agents** | Direct Python API | All tools + agent methods |
| **LangChain Agents** | MCP bridge/wrapper | All tools via MCP bridge |
| **AutoGPT/AgentGPT** | MCP client integration | All dev tools via protocol |
| **Crew.ai Agents** | Tool integration | Selected tools as Crew tools |

#### **🔧 Multiple Server Configurations**

```python
# 1. Core Agent Only (development tools)
from dev_tools.mcp_server import CoreAgentMCPServer
core_server = CoreAgentMCPServer(settings)

# 2. RAG Agent Only (production Q&A)
from src.mcp.mcp_server import RAGAgentMCPServer
rag_server = RAGAgentMCPServer(settings)

# 3. Integrated Server (both capabilities)
from dev_tools.mcp_server import IntegratedMCPServer
integrated_server = IntegratedMCPServer(settings)
```


#### **📡 Universal Connection & Integration**

See [DOCUMENTATION.md](DOCUMENTATION.md#integration) for:
- Universal connection methods (MCP, HTTP, Python import)
- Integration examples for MCP, LangChain, and custom agents
- List of all available tools and their parameters

**Quick links:**
- [API & Tool Reference](DOCUMENTATION.md#tool-reference)
- [Usage Examples](DOCUMENTATION.md#usage-examples)

**Summary:**
Any MCP-compatible agent (Claude, GPT, Strands Expert, LangChain, etc.) can connect to the StrandsCoreAgent via MCP, HTTP, or direct Python import. All tools (code quality, documentation, project assessment, etc.) are available through a unified interface. See [DOCUMENTATION.md](DOCUMENTATION.md) for full details and code samples.


## StrandsCoreAgent vs External MCP Servers

### **🤖 Custom Agent vs AWS Documentation MCP Server**

Understanding when to use StrandsCoreAgent versus external MCP services like AWS Documentation Server.


#### **📊 Feature Comparison**

See [DOCUMENTATION.md](DOCUMENTATION.md#strandscoreagent-vs-aws-documentation-mcp) for a detailed feature matrix and integration patterns.


#### **🎯 AWS Documentation MCP Server & StrandsCoreAgent Advantages**

See [DOCUMENTATION.md](DOCUMENTATION.md#aws-documentation-mcp-server) for:
- VS Code configuration for AWS Documentation MCP
- Advantages and limitations of AWS Documentation MCP
- Deep project integration and automation with StrandsCoreAgent
- Example: Combined workflow using both agents
- Use case decision matrix


### 5. **Confidence and Measurement**

See [DOCUMENTATION.md](DOCUMENTATION.md#confidence-and-measurement) for details on structured outputs, confidence scores, and measurable results.


### 6. **Development Workflow Enhancement**

See [DOCUMENTATION.md](DOCUMENTATION.md#development-workflow-enhancement) for:
- When to use GitHub Copilot vs StrandsCoreAgent
- Use case matrix and workflow recommendations
- Key value proposition and summary

**Summary:**
StrandsCoreAgent complements GitHub Copilot by providing deep, specialized analysis, structured outputs, and measurable results for code quality, documentation, and project health. Use Copilot for rapid code generation and StrandsCoreAgent for comprehensive analysis and automation.
