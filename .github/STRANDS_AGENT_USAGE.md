# Strands Expert Copilot Agent - Usage Guide

Complete documentation for the **Strands Agent Expert** GitHub Copilot agent and **Strands Generator** prompt.

## 🚀 Quick Start

### 1. Using the Strands Expert Agent

**In VS Code Copilot Chat:**
```
@strands-expert Create a document analysis agent
```

**Available immediately after creation** - no installation needed!

### 2. Using the Strands Generator Prompt

**In VS Code Copilot Chat:**
```
/strands-generator task_type:agent agent_name:MyAgent model_type:fast
```

**Generates instant boilerplate** following project patterns.

## 📋 Complete Usage Examples

### Agent Development Scenarios

#### 🏗️ **Creating New Agents**
```
@strands-expert Create a semantic search agent for documents

Response: Creates complete 3-node architecture with:
- TopicValidator (fast model, ~100ms)
- SecurityChecker (fast model, pattern matching)
- SearchWorker (powerful model, vector search tools)
```

#### 🔧 **Adding Tools**
```
@strands-expert Add a PDF extraction tool to my agent

Response: Provides @tool decorator function with:
- Proper type hints and error handling
- MCP integration patterns
- Integration with existing agent
```

#### ⚡ **Performance Optimization**
```
@strands-expert My RAG agent is too slow, optimize it

Response: Analyzes current implementation and suggests:
- Model tier adjustments (fast vs powerful)
- Early exit patterns for cost savings
- Caching strategies for embeddings
```

#### 🔍 **Debugging Issues**
```
@strands-expert Tool not appearing in MCP server, what's wrong?

Response: Troubleshoots:
- @tool decorator usage
- MCP server registration
- Tool schema validation
- Import/export issues
```

## 🛠️ Generator Prompt Reference

### Complete Syntax Options

#### **Agent Generation**
```bash
/strands-generator task_type:agent agent_name:DocumentProcessor model_type:powerful

# Generates:
# - Complete 3-node architecture
# - ValidationResult models
# - Proper tool integration
# - Cost-optimized routing
```

#### **Tool Creation**
```bash
/strands-generator task_type:tool tool_name:extract_metadata

# Generates:
# - @tool decorated function
# - Type hints and validation
# - Error handling patterns
# - MCP-compatible schema
```

#### **MCP Integration**
```bash
/strands-generator task_type:mcp tool_name:analyze_sentiment

# Generates:
# - MCP server registration
# - Tool schema definitions
# - Request/response handlers
# - Integration boilerplate
```

#### **Validation Patterns**
```bash
/strands-generator task_type:validation

# Generates:
# - ValidationResult Pydantic models
# - Routing decision structures
# - Error categorization enums
# - Type-safe response formats
```

#### **Routing Logic**
```bash
/strands-generator task_type:routing

# Generates:
# - Conditional routing patterns
# - Early exit optimization
# - Cost-saving decision trees
# - Performance monitoring
```

## 🎯 Real-World Development Workflow

### **Scenario: Building a Code Review Agent**

**Step 1: Plan the Architecture**
```
@strands-expert I need to build a code review agent that analyzes Python files for quality issues
```

**Step 2: Generate Base Structure**
```
/strands-generator task_type:agent agent_name:CodeReviewAgent model_type:powerful
```

**Step 3: Add Specialized Tools**
```
/strands-generator task_type:tool tool_name:analyze_complexity
/strands-generator task_type:tool tool_name:check_style_violations
/strands-generator task_type:tool tool_name:detect_security_issues
```

**Step 4: Integrate with MCP**
```
/strands-generator task_type:mcp tool_name:review_file
```

**Step 5: Optimize Performance**
```
@strands-expert How can I make this code review agent faster and cheaper?
```

## 🏆 Best Practices from the Agent

### **Cost Optimization Patterns**
- Fast models (qwen2.5:0.5b) for validation → 60-70% cost savings
- Early exit routing → Avoid expensive calls for invalid queries
- Structured Pydantic models → Type-safe routing decisions

### **3-Node Architecture Benefits**
- **Scalability**: Independent model scaling per node
- **Cost Control**: Pay only for complexity you need
- **Reliability**: Fail fast on invalid/malicious input
- **Observability**: Clear performance metrics per stage

### **Tool Design Guidelines**
- Single responsibility per tool
- Comprehensive type hints and validation
- Proper error handling and logging
- MCP-compatible schemas
- Integration with existing infrastructure

## 🚀 Advanced Usage Patterns

### **Multi-Agent Orchestration**
```
@strands-expert Design a pipeline with multiple specialized agents

Response: Suggests orchestration patterns with:
- Agent handoff protocols
- Shared state management
- Error propagation strategies
- Performance monitoring across agents
```

### **AgentCore vs Strands Decision**
```
@strands-expert Should I use AgentCore or Strands for my deployment?

Response: Provides decision matrix based on:
- Deployment target (Lambda vs Container vs Local)
- Model preferences (Bedrock vs Ollama vs OpenAI)
- Control requirements (Fine-grained vs Managed)
- Cost considerations (Per-request vs Fixed)
```

### **Integration with Existing Systems**
```
@strands-expert Integrate my agent with the existing Milvus RAG pipeline

Response: Shows integration patterns for:
- Vector database connectivity
- Embedding cache utilization
- Response caching strategies
- MCP server coordination
```

## 📚 Learning Resources

### **Generated Code Quality**
- ✅ **Type Safe**: All generated code includes proper type hints
- ✅ **Project Aware**: Follows established patterns from your codebase
- ✅ **Production Ready**: Includes error handling and logging
- ✅ **Optimized**: Cost and performance considerations built-in

### **When to Use Which Tool**

| Need | Use | Example |
|------|-----|---------|
| Complete new agent | `@strands-expert` | "Create a sentiment analysis agent" |
| Quick boilerplate | `/strands-generator` | Generate tool template |
| Debugging/optimization | `@strands-expert` | "Why is my agent slow?" |
| Architecture advice | `@strands-expert` | "Best pattern for multi-step workflow?" |
| Code templates | `/strands-generator` | MCP integration boilerplate |

## 🔧 Troubleshooting

### **Agent Not Appearing**
- Ensure files are in `.github/agents/` directory
- Check YAML frontmatter syntax (no tabs, proper quotes)
- Restart VS Code if needed

### **Generator Not Working**
- Use exact syntax: `/strands-generator task_type:agent`
- Check parameter spelling and values
- Ensure prompt file is in `.github/prompts/`

### **Getting Generic Responses**
- Make sure to use `@strands-expert` prefix
- Be specific about Strands/AgentCore context
- Reference project files or patterns when possible

## 💡 Pro Tips

1. **Combine Both Tools**: Use generator for boilerplate, agent for customization
2. **Be Specific**: Mention model preferences, deployment targets, performance needs
3. **Reference Project**: Point to existing code patterns for consistency
4. **Iterate**: Start with generator, refine with expert agent guidance
5. **Test Integration**: Verify generated code works with your existing MCP/RAG setup

---

**Ready to build better Strands Agents faster!** 🚀

Start with `@strands-expert` for any Strands Agent question or `/strands-generator` for quick code templates.
