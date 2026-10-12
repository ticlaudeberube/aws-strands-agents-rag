# Recent Changes

**Last Updated**: April 12, 2026

## Query Routing & UI Bug Fixes (April 12, 2026)

### Critical Bug Fixes
- **Topic Validation Parser Fix**: TopicChecker agent now correctly parses "YES/NO" responses instead of "true/false", fixing out-of-scope query rejection
- **Query Routing Order Fix**: Time-sensitive query detection moved after topic validation, preventing off-topic queries (like weather) from bypassing scope checks
- **Web Search Button Restoration**: Fixed health endpoint `web_search_enabled` field to check Tavily API key availability instead of supplement setting, restoring web search UI button
- **Enhanced Competitor Detection**: Improved logic to catch technical queries like "pinecone database features" or "weaviate vector search" that previously bypassed detection and caused hallucination
- **Error Message Consolidation**: Implemented DRY principles with centralized `_create_web_search_unavailable_message()` utilities, eliminating 13+ duplicate error messages

### Architecture Improvements
- **Proper Validation Pipeline**: Out-of-scope queries now exit at topic validation (Node 1) before reaching time-sensitive or web search logic
- **Consistent Error Handling**: All web search unavailable messages now use unified utility functions for maintainability
- **React UI Type Safety**: Enhanced multi-layer type safety for chat message rendering to prevent "[object Object]" display issues

### Files Modified
- `src/agents/strands_graph_agent.py`: Topic validation parsing, query routing order, DRY error messaging
- `api_server.py`: Health endpoint web search availability logic
- `chatbots/react-chatbot/src/App.js`: Type safety improvements
- `docs/`: Updated API_SERVER.md, DEVELOPMENT.md, QUERY_ROUTING.md with recent fixes

## Development Environment & Code Quality (April 8, 2026)

### Pre-commit Git Hooks Configuration
Automated code quality checks now run before each git commit:

- **Ruff Linting** — Code style and import ordering
- **Ruff Formatting** — 100-character line length enforcement
- **MyPy Type Checking** — Python type safety validation
- **Pytest** — Unit/integration test execution
- **File Validators** — Trailing whitespace, newlines, merge conflicts, YAML

**Setup Command:**
```bash
source .venv/bin/activate
pre-commit install
```

**Files Added/Modified**:
- `.pre-commit-config.yaml` (already in repo, now documented)
- `.vscode/extensions.json` (new: recommended extensions)
- `.vscode/settings.json` (AWS MCP server enabled)
- `.gitignore` (selective tracking: `.vscode/settings.json` and `.vscode/extensions.json`)
- `docs/DEVELOPMENT.md` (comprehensive hook guide)
- `docs/GETTING_STARTED.md` (pre-commit setup steps)

### Python Environment Fix
- Fixed venv path from `source venv/` to standard `.venv/`
- Upgraded Python from 3.9.6 to 3.12 for full compatibility
- All dev tools now properly installed and functional

### VS Code Extensions
Added 13 recommended extensions for team consistency:
- Python development (Pylance, black-formatter, ruff, mypy)
- AWS development (AWS Toolkit)
- Git tools (GitLens)
- Docker support
- REST client for API testing
- Remote development (containers, SSH)
- Markdown documentation

### AWS MCP Server Integration
- AWS MCP server now configured for Copilot coding improvements
- Not for tool execution, only for enhanced context and suggestions
- Configuration in `.vscode/settings.json` and global `mcp.json`

## UI Improvements

### Source Type Badges
Messages now show colored badges indicating the source of the answer:

- **⚡ CACHED** (gray) - Answer from response cache (<50ms)
- **🔍 KB** (green) - Knowledge base search (1-2s)
- **🌐 Web** (blue) - Web search results (3-6s)

**Files Changed**:
- `chatbots/react-chatbot/src/components/ChatMessage.js`
- `chatbots/react-chatbot/src/components/ChatMessage.css`

### Console Logging for Development
Browser console now shows active mode when sending queries:

- `💾 Cache enabled` - Normal mode with caching
- `🚫 BYPASS CACHE ACTIVE` - Fresh KB query mode
- `🌐 FORCE WEB SEARCH ACTIVE` - Web-only search mode

**Files Changed**: `chatbots/react-chatbot/src/App.js`

## Web Search Enhancements

### Improved Prompt Engineering
Web search now uses strict prompts to ensure LLM quotes actual web snippets instead of using training data:

```
CRITICAL INSTRUCTIONS:
1. Answer EXCLUSIVELY using the provided web search snippets
2. DO NOT use training knowledge - only cite what's in the snippets
3. Cite sources using HTML links
```

**Files Changed**: `src/agents/prompts.py`

### Debug Logging
API server now logs web search context for debugging:

```bash
[WEB_CONTEXT] Built context from 5 sources:
  [1] Milvus (vector database) - Wikipedia: Milvus is an open-source...
  [2] Introduction To Milvus: Milvus provides scalable...
```

**Files Changed**: `src/agents/strands_graph_agent.py`

## Documentation Updates

### New Documents
- **Production Readiness Guide** (`docs/PRODUCTION_READINESS.md`)
  - Security fixes (CORS, API keys, rate limiting)
  - Monitoring setup (Sentry, logging)
  - Pre-production checklist
  - 4-week implementation timeline

### Updated Documents
- **WEB_SEARCH_INTEGRATION.md** - Simplified and updated for web-only mode
- **chatbots/react-chatbot/README.md** - Added UI controls documentation
- **API_SERVER.md** - Clarified `bypass_cache` parameter usage

### Removed Obsolete Content
- Old "supplementary" web search references (replaced with web-only mode)
- Outdated cache behavior descriptions
- Legacy commit references (commit a0f1c64)

## Features Summary

| Feature | Status | How to Use |
|---------|--------|------------|
| **Web-Only Search** | ✅ Live | Click 🌐 button in UI or set `force_web_search: true` |
| **Cache Bypass** | ✅ Live | Click 🚫 button in UI or use `?bypass_cache=true` |
| **Source Badges** | ✅ Live | Automatic - shows on all responses |
| **Console Logging** | ✅ Live | Open browser DevTools → Console tab |

## Breaking Changes

None - all changes are backward compatible.

## Migration Notes

No migration needed. Changes are:
- UI improvements (automatic)
- Better logging (opt-in via browser console)
- Documentation updates only

## Next Steps

For production deployment, see:
- [Production Readiness Guide](PRODUCTION_READINESS.md)
- [Web Search Integration](WEB_SEARCH_INTEGRATION.md)
- [React Deployment](REACT_DEPLOYMENT.md)
