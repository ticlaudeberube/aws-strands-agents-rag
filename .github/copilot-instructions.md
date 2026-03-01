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
