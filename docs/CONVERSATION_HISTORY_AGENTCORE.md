# Conversation History - AgentCore-Compatible Implementation

## Overview

This document describes the conversation history pattern implemented in the chatbot that is **fully compatible with AWS Bedrock AgentCore** migration. The implementation focuses on portable infrastructure rather than custom persistence logic.

## What Was Implemented (Portable)

### 1. **Message Structure with Timestamps**
- Frontend now adds ISO 8601 timestamps to each message
- Backend API accepts `timestamp` in Message model
- Format: `{ role, content, timestamp }`

**Why this matters for AgentCore:**
- AgentCore Memory uses sequential timestamps for message ordering
- This structure matches `AgentCoreMemorySessionManager` expectations
- No rework needed when migrating

### 2. **Full Conversation History in API Requests**
- React frontend sends **all** messages instead of just the current one
- API receives conversation history as array: `conversationMessages`
- Messages are preserved in order with timestamps

**Code path (Strands Agent standard format):**
```javascript
// React: App.js - Wraps content in Strands ContentBlock format
const conversationMessages = messages
  .filter(m => m.role && m.text)
  .map(m => ({ 
    role: m.role, 
    content: [{ text: m.text }],  // Strands format: content is list of ContentBlocks
    timestamp: m.timestamp 
  }))
  .concat([{ 
    role: 'user', 
    content: [{ text: text }],  // Strands format
    timestamp: new Date().toISOString() 
  }]);

body: JSON.stringify({ messages: conversationMessages, ... })
```

```python
# Backend: api_server.py - Receives Strands format
conversation_history = [
    { 
        "role": msg.role, 
        "content": msg.content,  # Already [{ text: "..." }]
        "timestamp": msg.timestamp 
    }
    for msg in request.messages
]
```

### 3. **OpenAI-Compatible API Contract**
- All endpoints accept `messages` array
- Follows OpenAI Chat Completions API format
- Same signature used by AgentCore Runtime

**Endpoints updated:**
- `POST /v1/chat/completions` (non-streaming)
- `POST /v1/chat/completions/stream` (streaming)

## What Was NOT Implemented (AgentCore Provides These)

❌ **Message Persistence/Storage**
- AgentCore Memory handles this via `AgentCoreMemorySessionManager`
- No custom database layer needed

❌ **Session Management**
- AgentCore provides session lifecycle management
- Automatic session creation, state tracking

❌ **History Loading**
- AgentCore's `session_manager.list_messages()` loads conversation history
- No custom loading logic needed

❌ **Long-Context Compaction**
- AgentCore provides `CompactingSessionManager` for automatic summarization
- Handles token limits transparently

❌ **Memory Strategies**
- AgentCore defines memory retrieval strategies (preferences, facts, summaries)
- Configured via `AgentCoreMemoryConfig`

## Migration Path: Current → AgentCore

### Phase 1: Current System (← You are here)
```
React Frontend
    ↓
Full message history + timestamps
    ↓
OpenAI-compatible API
    ↓
StrandsRAGAgent (simple RAG)
```

### Phase 2: AgentCore Migration
```
React Frontend (same code!)
    ↓
Full message history + timestamps (same format!)
    ↓
OpenAI-compatible API (same interface!)
    ↓
AgentCore Runtime
    ↓
Session Manager + Memory (replaces custom logic)
    ↓
Strands Agent with context
```

**No changes needed to:**
- React frontend message sending
- API endpoint structure
- Message format/schema

**Changes when migrating:**
- Replace simple agent backend with AgentCore Runtime
- Add `AgentCoreMemorySessionManager` initialization
- Configure `AgentCoreMemoryConfig` with memory ID
- Strands Agent automatically receives full conversation context

## Technical Details

### Message Model (api_server.py)
```python
class Message(BaseModel):
    """Chat message - Strands Agent standard format with optional timestamp."""
    role: str                                    # "user" | "assistant" | "system"
    content: List[Dict[str, Any]]               # Strands ContentBlocks: [{"text": "..."}, {"toolUse": ...}, etc.]
    timestamp: Optional[str] = None             # ISO 8601 format for message ordering
```

### Conversation History Structure
```python
# Built in both endpoints (Strands Agent format):
conversation_history = [
    {
        "role": "user",
        "content": [{"text": "What is Milvus?"}],  # Content is list of ContentBlocks
        "timestamp": "2026-02-28T10:30:00.000Z"
    },
    {
        "role": "assistant",
        "content": [{"text": "Milvus is a vector database..."}],  # Same format for responses
        "timestamp": "2026-02-28T10:30:05.000Z"
    },
    ...
]
```

### Frontend Timestamp Generation
```javascript
// Each message gets an ISO 8601 timestamp on creation
const userMessage = {
    id: nextIdRef.current++,
    text: text,
    role: 'user',
    timestamp: new Date().toISOString(),  // ← Added
};
```

## Logging & Observability

API logs now show conversation size:
```
INFO: Processing 5 messages in conversation
INFO: Stream Query: What about latency? (conversation history: 5 messages)
```

This helps track conversation growth and context depth.

## Future: Using Conversation History

When AgentCore is integrated, conversation history can be used by the agent:

```python
# Future: StrandsAgent can access conversation context
class StrandsRAGAgent:
    def answer_question(
        self,
        question: str,
        conversation_history: Optional[List[Dict]] = None,  # Ready for use
        **kwargs
    ) -> Tuple[str, List[Dict]]:
        # Can detect clarifications:
        #   "latency" after "compare Milvus to other databases"
        # Can maintain context:
        #   "that one" referring to previous database mentioned
        # Can provide better answers with full context
        pass
```

## AgentCore Migration Checklist

When you're ready to integrate AWS Bedrock AgentCore, use this checklist:

### Phase 1: Setup (No Code Changes)
- [ ] Create AgentCore Memory resource via CDK/CloudFormation
- [ ] Get Memory ID and Region
- [ ] Set `MEMORY_ID` environment variable
- [ ] Install `bedrock-agentcore` SDK

### Phase 2: Backend Updates (Delete, Don't Add)

**Delete this code** (in `api_server.py` both endpoints):
```python
# DELETE THESE LINES (conversation_history building):
# Lines ~718-728 in chat_completions()
# Lines ~852-862 in chat_completions_stream()
# 
# conversation_history = [
#     {
#         "role": msg.role,
#         "content": msg.content,
#         "timestamp": msg.timestamp,
#     }
#     for msg in request.messages
# ]
```

**Add this code** (once per startup):
```python
# In api_server.py initialization:
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

memory_config = AgentCoreMemoryConfig(
    memory_id=os.environ.get("MEMORY_ID"),
    session_id=session_id,
    actor_id=user_id,
    enable_prompt_caching=True
)

session_manager = AgentCoreMemorySessionManager(
    agentcore_memory_config=memory_config
)

agent = Agent(session_manager=session_manager)
```

**That's it** - `agent.messages` will be auto-populated by SessionManager

### Phase 3: No Frontend Changes Needed
- ✅ Keep React sending full `messages` array
- ✅ Keep timestamps (they're already in the code)
- ✅ Keep API endpoints exactly as-is
- ❌ Don't change Message model
- ❌ Don't change ChatCompletionRequest

### Phase 4: Verify
- Test multi-turn conversation loads history
- Check AgentCore Memory dashboard for session events
- Verify timestamps are correct in Memory

## Code Locations with Migration Notes

These files already have `MIGRATION` comments for future reference:

1. **chatbots/react-chatbot/src/App.js** (line ~78)
   - Conversation message building

2. **api_server.py** (multiple locations)
   - Line ~44: Message model definition
   - Line ~720: conversation_history building in chat_completions()
   - Line ~817: Streaming endpoint docstring
   - Line ~854: conversation_history building in chat_completions_stream()

Just search for `MIGRATION` or `AGENTCORE` to find all relevant sections.

## Key Differences: Current vs. AgentCore

| Aspect | Current | AgentCore |
|--------|---------|-----------|
| Message storage | React state only | AgentCore Memory (persistent) |
| History loading | Frontend only | SessionManager auto-loads |
| Conversation limits | Browser memory (~100 msgs) | Managed by AgentCore (~1000s msgs) |
| Long context | Not handled | CompactingSessionManager + summarization |
| Cross-device history | ❌ Lost on refresh | ✅ Persistent across sessions |
| Message ordering | Frontend order | Timestamp-based ordering |

Everything else (API contract, message format, timestamps) **stays exactly the same**.

## References

- AWS Strands Agent: https://github.com/aws-samples/sample-strands-agent-with-agentcore
- AgentCore Memory Docs: https://docs.aws.amazon.com/bedrock-agentcore/
- Session Manager Integration: https://github.com/aws-samples/sample-strands-agent-with-agentcore/blob/main/chatbot-app/agentcore/src/agent/agent.py
