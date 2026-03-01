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
**Important**: Follow this documentation structure:
- **Global Project Documentation**: Located at project root
  - `README.md` - Main project overview and quick start (ONLY documentation at root level)
- **All Other Documentation**: Located in `docs/` folder
  - Feature guides: `docs/GETTING_STARTED.md`, `docs/LATENCY_OPTIMIZATION.md`, etc.
  - Technical references: `docs/API_SERVER.md`, `docs/CACHING_STRATEGY.md`, etc.
  - Development guides: `docs/DEVELOPMENT.md`, `docs/PROJECT_SUMMARY.md`, etc.

**When Updating Documentation**:
- If adding/modifying getting started → update `docs/GETTING_STARTED.md`
- If adding/modifying API endpoints → update `docs/API_SERVER.md`
- If adding/modifying performance → update `docs/LATENCY_OPTIMIZATION.md`
- If documenting a new feature → create in `docs/FEATURE_NAME.md`
- If updating project-level info → update root `README.md` ONLY
- **Never** create documentation files outside `docs/` folder (except `README.md`)

**Consolidation Rule**: 
- Avoid duplicate documentation across multiple files
- Consolidate related topics into single comprehensive guides
- Use cross-references (links) to related documentation instead of copy-pasting content

## Feature development guidelines
- You should not implement new features without implicitly requesting  permission to do so. Always ask for clarification and approval before implementing new features or making significant changes to the codebase. This ensures that all changes align with project goals and maintain code quality.

When developing new features or making changes to the codebase:
## Helpful Commands
- Document loaders: `document-loaders/load_milvus_docs_ollama.py`
- Interactive chat: `python chatbots/interactive_chat.py`
- API server: `python api_server.py`
- Run tests: `pytest`
- Run with coverage: `pytest --cov`
