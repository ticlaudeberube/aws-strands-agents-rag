# GitHub Copilot Instructions

## Project Context
This is an AWS Strands Agents RAG system that uses Milvus for vector database operations and implements Retrieval Augmented Generation (RAG) patterns.

## Documentation References
- **Milvus Documentation**: Located in `document_loaders/milvus_docs/en/`
  - Reference this documentation when providing suggestions for Milvus integration
  - Use the Milvus docs for API recommendations and best practices
  - Link to local Milvus documentation whenever relevant
- **Strands Agent Expert**: Specialized Copilot agent for Strands development
  - **Usage Guide**: [STRANDS_AGENT_USAGE.md](.github/STRANDS_AGENT_USAGE.md) - Complete documentation
  - **Agent**: `@strands-expert` - Expert assistance for Strands Agent development
  - **Skill**: `/strands-agent-development` - Project-aware workflow for implementing and testing Strands Agent changes
  - Use the skill for code changes; use the expert agent for design questions and troubleshooting
## Knowledge Base References
  - **AWS Strands Agent Samples**: https://github.com/aws-samples/sample-strands-agent-with-agentcore
    - Reference for sample Strands agent implementations
    - Use for patterns on integrating AWS Strands agents with other frameworks

## Code Structure
- `src/agents/` - AI agent implementations
- `src/tools/` - Tools including MilvusVectorDB wrapper
- `document_loaders/` - Document loading and embedding utilities
- `chatbots/` - Chatbot implementations (interactive and React)
- `chatbots/react-chatbot/e2e/` - **Playwright E2E tests** (test files documented below)
- `tests/` - Unit and integration tests (Python/pytest)

## Key Guidelines
0. **Architecture Isolation**: Read [src-isolation.instructions.md](.github/instructions/src-isolation.instructions.md) - Critical rule: `src/` must NEVER import from `document_loaders/`, and vice versa. Keep them independent.
1. **Milvus Integration**: When suggesting Milvus-related code, refer to `document_loaders/milvus_docs/en/` for proper API usage
2. **Vector Database**: Refer to `src/tools/` for existing MilvusVectorDB implementations
3. **RAG Pattern**: Consider the full RAG pipeline when suggesting code changes
4. **Document Loading**: Reference document loaders in `document_loaders/` for embedding and indexing workflows
5. **Documentation Updates**: When making changes to user-facing code, scripts, or instructions, update corresponding documentation files to reflect the changes. This includes updating setup instructions, command paths, and error messages.

## Strands Agent Development

### Architecture Pattern: 3-Node Conditional Routing (Real Implementation)

The project implements an **actual, executable 3-node Strands agent workflow** with real conditional routing:

```
User Query
    ↓
┌─────────────────────────────────────────────┐
│ 1. TOPIC CHECKER (Fast Model)               │ ← Validates if query is in-scope
│    - Strands Agent instance                 │   - Early exit on out-of-scope
│    - Fast model: qwen2.5:0.5b (~100ms)      │   - Cost optimization
│    - Returns validation result              │
└────────────┬────────────────────────────────┘
             ↓ (if valid)
┌─────────────────────────────────────────────┐
│ 2. SECURITY CHECKER (Fast Model)            │ ← Detects malicious queries
│    - Strands Agent instance                 │   - Blocks attacks early
│    - Pattern matching + LLM fallback        │   - Returns validation result
└────────────┬────────────────────────────────┘
             ↓ (if safe)
┌─────────────────────────────────────────────┐
│ 3. RAG WORKER (Powerful Model + Tools)      │ ← Generates answer
│    - Strands Agent with @tool decorators    │   - Uses cached embeddings
│    - search_knowledge_base() tool           │   - search_knowledge_base()
│    - generate_response() tool               │   - generate_response()
│    - Powerful model: llama3.1:8b (~1500ms)  │   - Returns: RAGResult
└────────────┬────────────────────────────────┘
             ↓
          Answer with Sources
```

### Real Strands Agent Implementation

When creating Strands agents in this project, follow this established pattern:

```python
# NOTE: These are the real imports and API surface used in
# src/agents/strands_graph_agent.py. Always confirm against that file
# before copying — do not guess method signatures.
from strands import Agent
from strands.tools import tool

# Node 1: Fast validation agent (no tools)
topic_agent = Agent(
    name="TopicChecker",
    system_prompt=prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS,
    model=fast_model,  # Fast model (e.g. qwen2.5:0.5b) for cost efficiency
    tools=[],
)

# Node 2: Fast security agent (no tools)
security_agent = Agent(
    name="SecurityChecker",
    system_prompt=prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS,
    model=fast_model,  # Fast model for cost efficiency
    tools=[],
)

# Node 3: Powerful RAG agent with tools
@tool
def search_knowledge_base(
    question: str, collections: list[str], top_k: int = 5
) -> dict[str, Any]:
    """Search the knowledge base for relevant documents."""
    return retrieval_tool(question, collections, top_k)

@tool
def generate_response(
    question: str, context: str, sources: list[dict], temperature: float | None = None
) -> dict[str, Any]:
    """Generate an answer based on context and sources."""
    return generation_tool(question, context, sources, temperature)

rag_agent = Agent(
    name="RAGWorker",
    system_prompt=prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.format(
        formatting_rules=prompts.FORMATTING_RULES
    ),
    model=rag_model,  # Powerful model (e.g. llama3.1:8b)
    tools=[search_knowledge_base, generate_response],
)

# Public entry point (see StrandsGraphRAGAgent.answer_question).
# Conditional routing (topic -> security -> RAG, with early exit on failure)
# happens inside the graph; the public method returns an (answer, sources)
# tuple, not a RAGResult.
async def answer_question(
    self,
    question: str,
    collection_name: str | None = None,
    collections: list[str] | None = None,
    top_k: int = 5,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> tuple[str, list[dict]]:
    """Answer a question using the 3-node RAG graph."""
    ...
    return answer_text, sources_list
```

### Structured Output Models

```python
# Mirrors src/agents/strands_graph_agent.py. These are internal routing
# models; the public answer_question() returns an (answer, sources) tuple.
class ValidationResult(BaseModel):
    is_valid: bool = Field(..., description="Whether the query passes validation")
    reason: str = Field(..., description="Explanation for the validation result")
    category: str | None = Field(
        None, description="Category of failure if invalid (security_risk, out_of_scope)"
    )

class RAGResult(BaseModel):
    answer: str = Field(..., description="Generated answer to the query")
    sources: list[dict] = Field(default_factory=list, description="Source documents used")
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence 0-1")
```

### Cost-Optimization Pattern

Key benefit of this architecture (figures below are illustrative, not
measured — early exit avoids the expensive RAG node on invalid queries):

```
Query Type           Path                                   Latency   Cost
─────────────────────────────────────────────────────────────────────────
Out-of-scope         TopicChecker reject                    ~fast     low
Security threat      TopicChecker → SecurityChecker reject   ~fast     low
Valid & safe query   All 3 nodes + RAG                       ~slow     high
```

The win comes from skipping the powerful RAG model whenever a fast validation
node rejects the query early.

### Testing Strands Agents

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_valid_query():
    """Test the complete workflow with a valid query.

    answer_question is async and returns an (answer, sources) tuple.
    """
    agent = StrandsGraphRAGAgent(Settings())
    answer, sources = await agent.answer_question("What is Milvus vector indexing?")
    assert answer
    assert isinstance(sources, list)
```

Node-level routing is driven by the `ValidationResult` model (`is_valid`,
`reason`, `category`). When testing individual nodes, assert against that
structured output rather than a raw string or a `.is_threat` attribute that
does not exist in this codebase.

### Common Patterns

**Pattern 1: Fast Models for Validation**
```python
# ✅ DO: Use 0.5-1B param models for checkers
topic_agent = Agent(name="TopicChecker", system_prompt=..., model=fast_model, tools=[])

# ❌ DON'T: Use 8B+ models for simple validation
topic_agent = Agent(name="TopicChecker", system_prompt=..., model=rag_model, tools=[])
```

**Pattern 2: Early Exit Prevents Downstream Execution**
```python
# ✅ DO: Return early from the rejection path so the RAG node never runs
if not topic_validation.is_valid:
    return reject_out_of_scope()  # RAGWorker never invoked

# ❌ DON'T: Keep processing after validation fails (wastes the powerful model)
```

**Pattern 3: @tool Decorator for Agent Tools**
```python
from strands.tools import tool

# ✅ DO: Mark functions passed to an Agent as Strands tools
@tool
def search_knowledge_base(
    question: str, collections: list[str], top_k: int = 5
) -> dict[str, Any]:
    """Search the knowledge base for relevant documents."""
    return retrieval_tool(question, collections, top_k)

# ❌ DON'T: Register a bare function on an Agent without the @tool decorator
```

### Playwright E2E Testing

The project includes Playwright E2E tests for the React chatbot under `chatbots/react-chatbot/e2e/`:

**Test Structure:**
```python
# tests/e2e/example.spec.ts
import { test, expect } from '@playwright/test';

test('should respond to valid question', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // Type question in input
  await page.fill('input[placeholder="Type your question..."]', 'What is Milvus?');
  await page.click('button:has-text("Send")');

  // Wait for response
  const response = await page.waitForSelector('[data-testid="response"]');
  await expect(response).toContainText('Milvus');
});

test('should display sources', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // Send question
  await page.fill('input[placeholder="Type your question..."]', 'test query');
  await page.click('button:has-text("Send")');

  // Verify sources appear
  const sources = await page.locator('[data-testid="sources"]');
  await expect(sources).toBeVisible();
});
```

**Running E2E Tests:**
```bash
# Install dependencies
cd chatbots/react-chatbot
npm install

# Start dev server (in background)
npm start &

# Run tests
npx playwright test

# Run tests in UI mode for debugging
npx playwright test --ui

# Run specific test file
npx playwright test e2e/chat.spec.ts
```

**Test Best Practices:**
- ✅ Use data-testid attributes for reliable element selection
- ✅ Wait for dynamic content (responses, sources) before assertions
- ✅ Test both happy path (valid queries) and error cases (out-of-scope, malformed)
- ✅ Isolate tests (no dependency between test cases)
- ✅ Use meaningful test names describing the user behavior
- ✅ Keep tests focused on user interactions, not implementation details
- ❌ Don't use hardcoded timeouts (use waitFor selectors instead)
- ❌ Don't test internal state directly (test visible UI behavior)
- ❌ Don't create test interdependencies (each test must be independent)

### Best Practices

✅ **DO**:
- Use fast models (500M-1B) for validation nodes (TopicChecker, SecurityChecker)
- Use powerful models (8B+) for answer generation (RAGWorker)
- Cache embeddings to avoid recomputation
- Return structured ValidationResult objects for routing
- Use meaningful agent names (TopicChecker, SecurityChecker, RAGWorker)
- Test each node independently with mocks
- Track execution path: ["topic_check", "security_check", "rag_worker"]
- Document branch logic in edge condition comments

❌ **DON'T**:
- Put expensive LLM calls in validation nodes (defeats early-exit optimization)
- Re-compute embeddings for the same question
- Return raw strings from validation nodes (need structured routing decision)
- Create monolithic agents that do too much
- Skip type hints on tool parameters
- Ignore Strands @tool/@agent decorators
- Use LangGraph or other graph frameworks (this project uses Strands)
- Use AgentCore patterns in the core application (reserved for serverless deployments only)


## Strands Agent Framework Notes

**Important**: This project uses **real Strands agents** (from `strands-agents>=1.27.0`) as the core implementation:
- ✅ Strands agents are the primary implementation (`src/agents/strands_graph_agent.py`)
- ✅ MCP server wraps Strands agents to expose tools (`src/mcp/mcp_server.py`)
- ❌ LangGraph (not used)
- ❌ Pseudo-code graph definitions (replaced with real Agent instances)

All agents are real `strands.Agent` instances (`from strands import Agent`), orchestrated by `StrandsGraphRAGAgent` with real conditional routing based on each node's structured response.

### Architecture Layers

**Layer 1: Strands Agents (Core Implementation)**
- Direct usage: `from strands import Agent`
- 3-node architecture: TopicChecker → SecurityChecker → RAGWorker
- Used in: `src/agents/strands_graph_agent.py`
- This is the primary development focus

**Layer 2: MCP Server (Interface/Exposure Layer)**
- Wraps StrandsGraphRAGAgent to expose tools in MCP format
- Used in: `src/mcp/mcp_server.py`
- Purpose: Enable external agents to call tools via Model Context Protocol
- Tools exposed: Search knowledge base, generate responses, etc.

**Layer 3: AgentCore (Optional Serverless Deployment)**
- Not currently integrated into core application
- Alternative deployment pattern for AWS Lambda + Bedrock
- See: `docs/DEPLOYMENT.md` for serverless deployment guidelines
- Only use AgentCore patterns if deploying to AWS Lambda with Bedrock agents

## Documentation Organization

### Rules

- All documentation lives in `docs/`; the only markdown allowed in the repo root is `README.md`.
- Keep `README.md` lean: overview, key features, a diagram, a short quick start, and the doc index. Link to `docs/` for anything longer (setup, config, code examples, troubleshooting).
- One canonical source per topic. Never duplicate content across files — cross-reference with relative links (`[text](docs/FILE.md#section)`) and update the canonical file only.
- When you change code, update the matching doc: config/env vars ↔ `docs/GETTING_STARTED.md` and `.env.example`; API endpoints ↔ `docs/API_SERVER.md`; setup commands ↔ `docs/GETTING_STARTED.md` and the README quick start.
- `docs/INDEX.md` is the source of truth for the active doc set. When adding or renaming a doc, update `INDEX.md` (and the README index if it's a major feature). Do not reference archived or non-existent files.

### Canonical Sources (see `docs/INDEX.md`)

| Topic | Canonical File |
|-------|---|
| Setup, installation, environment | `docs/GETTING_STARTED.md` |
| Practical usage / how-to, code examples | `docs/HOW_TO.md` |
| System architecture, mode selection, runtime flow | `docs/ARCHITECTURE.md` |
| REST API, endpoints, sample requests | `docs/API_SERVER.md` |
| Anti-hallucination design, thresholds, observability | `docs/ANTI_HALLUCINATION.md` |
| Local MLflow evaluation harness | `docs/EVAL_LOCAL.md` |
| Serverless/AWS (Terraform, Lambda, Bedrock) deployment | `docs/DEPLOYMENT.md` |
| Serverless local emulation | `docs/SERVERLESS_LOCAL.md` |
| Chatbot UI behavior | `docs/CHATBOT_GUI_FEATURES.md` |
| Docker, containers | `docker/README.md` |
| Testing | `tests/README.md` |

## Feature Development Guidelines

You should not implement new features without explicitly requesting permission to do so. Always ask for clarification and approval before implementing new features or making significant changes to the codebase. This ensures that all changes align with project goals and maintain code quality.

When developing new features or making changes to the codebase:
- **Always** ask for approval before major changes
- **Always** update documentation simultaneously with code
- **Always** use canonical sources for documentation
- **Never** duplicate content across doc files
- **Never** put detailed content in README.md (link instead)
## Helpful Commands
- Document loaders: `uv run python document_loaders/load_milvus_docs_ollama.py`
- Interactive chat: `uv run python chatbots/interactive_chat.py`
- API server: `uv run python api_server.py`
- Run tests: `uv run pytest`
- Run with coverage: `uv run pytest --cov`

## Error Handling & Logging Standards

### Error Handling
- Use typed exceptions from src/config/settings.py or custom exception classes
- Avoid bare except clauses; always specify exception type
- Log errors with context: error type, source, and recovery action
- Propagate exceptions up with meaningful context preservation

### Logging Configuration
- Use Python's logging module (configured in settings.py)
- Log levels: DEBUG (dev info), INFO (state changes), WARNING (issues), ERROR (failures)
- Include correlation IDs in logs for request tracing
- Never log sensitive data (API keys, passwords, embeddings)

## Type Checking & Code Quality

### Type Hints
- All functions must have return type hints (required by mypy config)
- Use Union[Type1, Type2] or Type1 | Type2 for optional types
- Use generics for containers: List[str], Dict[str, Any]
- Run: `uv run mypy .` before committing

### Code Quality Enforcement
- **Linting**: `uv run ruff check --fix` (import sorting, complexity)
- **Formatting**: `uv run ruff format` (enforces 100-char lines)
- **Testing**: `uv run pytest --cov` (must pass with branch coverage)
- Pre-commit hooks run all checks - ensure they pass

### Import Organization
- Standard library → Third-party → Local imports (separate groups)
- One import per line for clarity
- Ruff automatically sorts with --fix
- Use explicit imports, avoid wildcard imports (from module import *)

## Environment Variable Management

### .env Configuration
- All runtime configuration in `.env.example` (includes all variables)
- Use pydantic-settings for validation and type coercion
- Never commit `.env` (contains secrets)
- Always update `.env.example` when adding new env vars
- Document new env vars in docs/GETTING_STARTED.md#configuration

### Settings Hierarchy
1. .env file (highest priority)
2. Environment variables (system-level)
3. pydantic defaults (lowest priority)

## MCP Server Development

### Model Context Protocol Interface

The MCP server (`src/mcp/mcp_server.py`) exposes Strands agent tools to external systems:

```
Strands Agents (Core) → MCP Server (Wrapper) → External Agents/Systems
```

**Key Responsibilities:**
- Initialize StrandsGraphRAGAgent and register its tools
- Expose tools in MCP-compatible format (schema, description, handling)
- Maintain mapping between tool definitions and Strands agent execution
- Handle tool invocation and response formatting

### Tool Registration
- Tools exposed via MCP must be registered in `src/mcp/mcp_server.py`
- Each tool requires: name, description, input schema, handler function
- Input validation: use Pydantic models for request schemas
- Response format: Always return structured data (dict/model, not raw strings)
- Error handling: Return {error: str} format for failures

### Tool Guidelines
- Tool names: snake_case, descriptive (not abbreviations)
- Keep tools focused on single responsibility
- Document with examples in docstrings
- Test tool registration and input validation
- Tools should delegate to Strands agents, not duplicate logic

## Testing Patterns

### Test Organization
- Unit tests (small, fast, mocked) in test_module.py
- Integration tests with @pytest.mark.integration
- Async tests with @pytest.mark.asyncio
- Slow tests (>1s) with @pytest.mark.slow

### Test Coverage Goals
- Minimum 80% statement coverage (current: 48%)
- All agent flows tested (happy path + error cases)
- All API endpoints tested (status, schemas, errors)
- Tool integration tested with mocks

### Test Patterns (AAA Format)
```python
@pytest.mark.asyncio
async def test_feature():
    # Arrange: set up test data
    agent = StrandsGraphRAGAgent(Settings())
    question = "test question"

    # Act: execute the code (answer_question is async, returns a tuple)
    answer, sources = await agent.answer_question(question)

    # Assert: verify results
    assert answer
    assert isinstance(sources, list)
```

### Tool Development Guidelines
## When Creating New Tools/Skills
- Place in src/tools/ or src/agents/skills/ (appropriate location)
- Implement required interface/base class
- Add comprehensive docstrings with examples
- Create unit tests (test_*.py pattern)
- Register in tool_registry.py if needed
- Update `docs/HOW_TO.md` with examples
- Consider caching strategy for expensive operations
## Vector Database Tools
- Use existing MilvusVectorDB in milvus_client.py
- Leverage embedding cache to avoid recomputation
- Always validate embeddings dimension match
- Document collection schemas in docstrings

## AWS AgentCore Development (Serverless Deployments)

### When to Use AgentCore Patterns

AgentCore is an alternative deployment pattern for serverless AWS Lambda + Bedrock agents. Use AgentCore guidance only when:
- Deploying to AWS Lambda (not container/Fargate)
- Using Amazon Bedrock agents (not local Ollama models)
- See: `docs/DEPLOYMENT.md` (serverless/AWS deployment) and `docs/SERVERLESS_LOCAL.md` (local serverless emulation)

### AgentCore vs. Strands for Local Development

**Use Strands Agents Pattern (Current):**
- Local development with Ollama
- Docker/container deployments
- Fine-grained control over agent orchestration
- Cost-optimized 3-node routing

**Use AgentCore for Serverless:**
- AWS Lambda with Bedrock models
- Managed agent lifecycle
- Auto-handled session management
- When AWS services are the constraint

**Important**: Do NOT mix AgentCore and Strands patterns in the same codebase. Choose one deployment model and follow its guidelines.

### AgentCore References
- **AWS Bedrock AgentCore**: https://github.com/awslabs/amazon-bedrock-agentcore-samples
- **Serverless/AWS deployment**: [DEPLOYMENT.md](../docs/DEPLOYMENT.md)
- **Serverless local emulation**: [SERVERLESS_LOCAL.md](../docs/SERVERLESS_LOCAL.md)
- **Known AWS deployment gaps**: [AWS_DEPLOYMENT_GAPS.md](../docs/AWS_DEPLOYMENT_GAPS.md)
