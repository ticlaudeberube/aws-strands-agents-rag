# GitHub Copilot Instructions

## Project Context
This is an AWS Strands Agents RAG system that uses Milvus for vector database operations and implements Retrieval Augmented Generation (RAG) patterns.

## Documentation References
- **Milvus Documentation**: Located in `document-loaders/milvus_docs/en/`
  - Reference this documentation when providing suggestions for Milvus integration
  - Use the Milvus docs for API recommendations and best practices
  - Link to local Milvus documentation whenever relevant
## Knowledge Base References
  - **AWS Strands Agent with AgentCore**: https://github.com/aws-samples/sample-strands-agent-with-agentcore
    - Reference this repository for sample implementations and best practices
    - Use for patterns on integrating AWS Strands agents with AgentCore framework
  - **Amazon Bedrock AgentCore Samples**: https://github.com/awslabs/amazon-bedrock-agentcore-samples
    - Reference for Bedrock-specific agent patterns and examples
    - Use for AgentCore framework implementation details

## Code Structure
- `src/agents/` - AI agent implementations
- `src/tools/` - Tools including MilvusVectorDB wrapper
- `document-loaders/` - Document loading and embedding utilities
- `chatbots/` - Chatbot implementations (interactive and React)

## Key Guidelines
1. **Milvus Integration**: When suggesting Milvus-related code, refer to `document-loaders/milvus_docs/en/` for proper API usage
2. **Vector Database**: Refer to `src/tools/` for existing MilvusVectorDB implementations
3. **RAG Pattern**: Consider the full RAG pipeline when suggesting code changes
4. **Document Loading**: Reference document loaders in `document-loaders/` for embedding and indexing workflows
5. **Documentation Updates**: When making changes to user-facing code, scripts, or instructions, update corresponding documentation files to reflect the changes. This includes updating setup instructions, command paths, and error messages.

## Strands Agent Development

### Architecture Pattern: 3-Node Graph Design

The project uses a specialized **3-node graph architecture** for RAG:

```
User Query
    ↓
┌─────────────────────────────────────────────┐
│ 1. TOPIC CHECKER (Fast Model)               │ ← Validates if query is in-scope
│    - Checks query relevance to knowledge    │   - Early exit on out-of-scope
│    - Returns: ValidationResult              │   - Cost optimization
└────────────┬────────────────────────────────┘
             ↓ (if valid)
┌─────────────────────────────────────────────┐
│ 2. SECURITY CHECKER (Fast Model)            │ ← Detects malicious queries
│    - Pattern matching: jailbreak, injection │   - Blocks attacks early
│    - LLM fallback for complex threats       │   - Returns: ValidationResult
└────────────┬────────────────────────────────┘
             ↓ (if safe)
┌─────────────────────────────────────────────┐
│ 3. RAG WORKER (Powerful Model)              │ ← Generates answer
│    - Vector search in Milvus                │   - Uses cached embeddings
│    - Answer generation with sources         │   - Returns: RAGResult
└────────────┬────────────────────────────────┘
             ↓
          Answer
```

### Node Implementation Pattern

When creating Strands agent nodes, follow this pattern:

```python
from src.agents.strands_graph_agent import ValidationResult, RAGResult

# Node functions receive state dict and return structured output
def topic_checker_node(state: dict) -> dict:
    """Validate if query is in-scope.

    Pattern:
    1. Extract input from state dict
    2. Perform validation logic
    3. Return structured ValidationResult
    4. Include reason for routing decision
    """
    question = state.get("question")

    # Your validation logic
    is_valid = check_relevance(question)

    # Return as dict (Strands converts to state)
    return {
        "validation": ValidationResult(
            is_valid=is_valid,
            reason="Query matches knowledge base scope" if is_valid else "Out of scope",
            category="out_of_scope" if not is_valid else None
        )
    }

def rag_worker_node(state: dict) -> dict:
    """Generate answer using RAG pipeline.

    Pattern:
    1. Extract retrieval context from state
    2. Search vector database (cache embeddings)
    3. Generate answer with sources
    4. Return RAGResult with confidence score
    """
    question = state.get("question")

    # Search vector database
    sources = vector_db.search(question, top_k=5)

    # Generate answer with LLM
    answer = llm.generate(question, context=sources)

    return {
        "result": RAGResult(
            answer=answer,
            sources=sources,
            confidence_score=0.85
        )
    }
```

### Structured Output Models

Use Pydantic models for routing and decision-making:

```python
# For routing decisions (checkpoint validation)
class ValidationResult(BaseModel):
    is_valid: bool                    # Route decision
    reason: str                       # Explanation for routing
    category: Optional[str]           # Type of rejection

# For final answers
class RAGResult(BaseModel):
    answer: str                       # Generated answer
    sources: List[Dict]              # Source documents used
    confidence_score: float = 0.5    # 0-1 confidence level
```

### Conditional Routing (Edge Functions)

Routes between nodes based on validation results:

```python
def should_proceed_to_security_check(state: dict) -> bool:
    """Router: Topic check passed?"""
    validation = state.get("validation")
    return validation.is_valid if validation else False

def should_proceed_to_rag(state: dict) -> bool:
    """Router: Security check passed?"""
    validation = state.get("validation")
    return validation.is_valid if validation else False

def create_rejection_response(state: dict) -> dict:
    """Create standardized rejection response."""
    validation = state.get("validation")
    return {
        "result": RAGResult(
            answer=f"I cannot answer this question. {validation.reason}",
            sources=[],
            confidence_score=0.0
        )
    }
```

### Skill Organization

Skills are organized in `src/agents/skills/`:

```
src/agents/skills/
├── __init__.py
├── retrieval_skill.py          # Vector search and document retrieval
├── answer_generation_skill.py  # LLM-based answer generation
└── knowledge_base_skill.py     # Knowledge base operations
```

**When creating a new skill**:
- One responsibility per skill file
- Use descriptive function names: `<action>_<target>` (e.g., `search_documents`, `validate_embedding`)
- Add type hints for all functions
- Include comprehensive docstrings
- Export main functions in `skills/__init__.py`

### Tool Creation for Strands Agents

Create reusable tools in `src/tools/`:

```python
def create_milvus_search_tool(vector_db: MilvusVectorDB, ollama_client: OllamaClient):
    """Create a tool function for Strands agent.

    Tools are callable functions that:
    1. Take arguments from agent node
    2. Perform external operations (DB, API calls)
    3. Return structured results
    4. Handle errors gracefully
    """
    def search_documents(
        question: str,
        collection_name: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Search vector database and return formatted results."""
        try:
            # Generate embedding with cache
            embedding = ollama_client.embed(question)

            # Search Milvus
            results = vector_db.search(
                embedding,
                collection_name=collection_name,
                limit=top_k
            )

            # Format and return
            return {
                "success": True,
                "documents": results,
                "count": len(results)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    return search_documents
```

### Common Patterns

**Pattern 1: Early Exit on Validation Failure**
```python
# Fast models check early → save costs
if not topic_check_result.is_valid:
    return rejection_response  # Don't call RAG worker
```

**Pattern 2: Caching at Node Level**
```python
# Cache embeddings to avoid recomputation
embedding = cache.get(question)
if embedding is None:
    embedding = ollama_client.embed(question)
    cache.set(question, embedding)
```

**Pattern 3: Conditional Tool Calls**
```python
# Don't call expensive tools if not needed
if requires_web_search:
    web_results = web_search_tool(question)
else:
    web_results = []
```

### Best Practices

✅ **DO**:
- Use separate, fast models for validation nodes (cost optimization)
- Cache expensive operations (embeddings, searches)
- Return structured outputs for routing decisions
- Use meaningful node names (TopicChecker, SecurityChecker, RAGWorker)
- Document branching logic in edge conditions
- Test each node independently with mocks
- Include execution tracing (log which nodes ran)

❌ **DON'T**:
- Put expensive LLM calls in validation nodes (defeats early-exit optimization)
- Re-compute embeddings for the same question
- Return raw strings from nodes that need routing decisions
- Create monolithic nodes that do multiple responsibilities
- Skip error handling in tool functions
- Ignore cache hits in tools

### Testing Strands Agents

```python
@pytest.mark.unit
def test_topic_checker_rejects_out_of_scope():
    """Test topic checker node."""
    state = {"question": "What is the capital of France?"}
    result = topic_checker_node(state)
    assert not result["validation"].is_valid
    assert result["validation"].category == "out_of_scope"

@pytest.mark.integration
def test_end_to_end_rag_flow():
    """Test complete graph execution."""
    workflow = create_rag_graph(settings)
    result = workflow.invoke("What is Milvus?")
    assert result.answer is not None
    assert len(result.sources) > 0
```

### Execution Tracking

Access execution details via GraphResult:

```python
result = workflow.invoke(question)

# See which nodes executed
print(f"Execution path: {result.execution_order}")
# ['topic_check', 'security_check', 'rag_worker']

# Check if rejected
if result.is_rejected:
    print(f"Rejection reason: {result.rejection_reason}")
```

## Documentation Organization

### Structure (DRY - Single Source of Truth)
- **README.md** (root): High-level overview, architecture diagrams, quick start, doc index **ONLY**
- **docs/GETTING_STARTED.md**: Complete setup, configuration, troubleshooting
- **docs/DEVELOPMENT.md**: Code examples, API usage, advanced features
- **docs/ARCHITECTURE.md**: System design, component overview, data flow
- **docs/API_SERVER.md**: REST endpoints, health checks, MCP details
- **docs/LATENCY_OPTIMIZATION.md**: Performance tuning, caching strategies
- **docs/*.md**: Feature/topic-specific guides (one file per major topic)

### README.md Rules (Keep It Lean)
✅ **Include**:
- Project description (1-2 sentences)
- Key features (bullet points)
- Architecture diagram (ASCII or Mermaid)
- Data flow diagram (visual only)
- Documentation index table linking to docs/
- Quick start (5-10 lines max, with link to full guide)
- Project structure overview

❌ **Never Include**:
- Setup details (link to `docs/GETTING_STARTED.md`)
- Configuration options (link to `docs/GETTING_STARTED.md#configuration`)
- Code examples beyond 5 lines (link to `docs/DEVELOPMENT.md`)
- Troubleshooting steps (link to `docs/GETTING_STARTED.md#troubleshooting`)
- Performance tips (link to `docs/LATENCY_OPTIMIZATION.md`)
- Docker commands (link to `docker/README.md`)
- Detailed roadmap (condensed version only)

### Documentation Consolidation (DRY Principle)
**Rule**: Never duplicate content across files
- If information exists in `docs/GETTING_STARTED.md`, don't repeat it in `docs/DEVELOPMENT.md`
- Use **cross-references** (links) instead of copy-pasting
- When updating a fact, update the canonical source only

**Canonical Sources**:
| Topic | Canonical File |
|-------|---|
| Setup, config, troubleshooting | `docs/GETTING_STARTED.md` |
| Code examples, API usage, features | `docs/DEVELOPMENT.md` |
| System architecture, components | `docs/ARCHITECTURE.md` |
| Performance, caching, optimization | `docs/LATENCY_OPTIMIZATION.md` |
| REST API, endpoints | `docs/API_SERVER.md` |
| Docker, containers | `docker/README.md` |
| Testing | `tests/README.md` |

### Documentation Index Updates
When creating/updating docs:
1. Update documentation table in README.md to include new resources
2. If creating new docs/FILE.md, add to appropriate category in table
3. Keep table up-to-date when moving or renaming files

### Configuration Changes
When updating `.env`, `settings.py`, or configuration:
- **Always** update `docs/GETTING_STARTED.md#configuration` section
- **Always** update `.env.example` with new variables
- Update `docs/LATENCY_OPTIMIZATION.md` if performance-related
- Update README.md only if major feature change
- Never document config in multiple files

### Feature Documentation
When adding new features:
1. Document in appropriate canonical file (see table above)
2. Add example code to `docs/DEVELOPMENT.md` or create focused guide
3. Add link to README.md documentation index (if major feature)
4. Don't create redundant "how-to" docs for the same feature

### Link Standards
- Use relative paths: `[text](docs/FILE.md)` or `[text](docs/FILE.md#section)`
- Link to specific sections when granular: `[Setup](docs/GETTING_STARTED.md#setup)`
- Use meaningful link text: `[Performance tips](docs/LATENCY_OPTIMIZATION.md)` not `click here`

### Documentation Updates When Code Changes
**Always synchronize**:
- Model names in `.env.example` ↔ `src/config/settings.py` ↔ docs
- Configuration variables ↔ `docs/GETTING_STARTED.md`
- API endpoints ↔ `docs/API_SERVER.md`
- Setup commands ↔ `docs/GETTING_STARTED.md` ↔ README quick start

## Documentation Quality Checklist

**Before submitting documentation changes:**
- [ ] No duplicate content exists in other files
- [ ] All cross-references use correct relative paths
- [ ] Code examples are in canonical file (`docs/DEVELOPMENT.md`)
- [ ] Setup/config steps are in `docs/GETTING_STARTED.md`
- [ ] All links are tested and working
- [ ] If code changed, docs updated to match
- [ ] README.md remains lean (<300 lines)
- [ ] No long lists or detailed procedures in README (linked instead)

## Feature Development Guidelines

You should not implement new features without explicitly requesting permission to do so. Always ask for clarification and approval before implementing new features or making significant changes to the codebase. This ensures that all changes align with project goals and maintain code quality.

When developing new features or making changes to the codebase:
- **Always** ask for approval before major changes
- **Always** update documentation simultaneously with code
- **Always** use canonical sources for documentation
- **Never** duplicate content across doc files
- **Never** put detailed content in README.md (link instead)
## Helpful Commands
- Document loaders: `document-loaders/load_milvus_docs_ollama.py`
- Interactive chat: `python chatbots/interactive_chat.py`
- API server: `python api_server.py`
- Run tests: `pytest`
- Run with coverage: `pytest --cov`

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

### Model Context Protocol
- Tools exposed via MCP must be registered in src/mcp/mcp_server.py
- Each tool requires: name, description, input schema, handler function
- Input validation: use Pydantic models for request schemas
- Response format: Always return structured data (dict/model, not raw strings)
- Error handling: Return {error: str} format for failures

### Tool Guidelines
- Tool names: snake_case, descriptive (not abbreviations)
- Keep tools focused on single responsibility
- Document with examples in docstrings
- Test tool registration and input validation

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
def test_feature():
    # Arrange: set up test data
    question = "test question"

    # Act: execute the code
    result = agent.answer(question)

    # Assert: verify results
    assert result.answer is not None
    assert result.sources is not []

### Tool Development Guidelines
## When Creating New Tools/Skills
- Place in src/tools/ or src/agents/skills/ (appropriate location)
- Implement required interface/base class
- Add comprehensive docstrings with examples
- Create unit tests (test_*.py pattern)
- Register in tool_registry.py if needed
- Update DEVELOPMENT.md with examples
- Consider caching strategy for expensive operations
## Vector Database Tools
- Use existing MilvusVectorDB in milvus_client.py
- Leverage embedding cache to avoid recomputation
- Always validate embeddings dimension match
- Document collection schemas in docstrings
