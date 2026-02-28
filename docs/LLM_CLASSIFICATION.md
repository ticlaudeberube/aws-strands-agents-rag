# LLM-Based Comparative Question Classification

## Overview

The comparative question detection has been refactored from a **hardcoded keyword-based approach** to an **LLM-based classification approach**.

## What Changed

### Before (Regex + Hardcoded Keywords)
- Used a hardcoded list of keywords: `["vs", "versus", "compared to", "comparison", ...]`
- Applied regex patterns to extract product names
- Fragile and required maintenance when adding new comparison patterns

### After (LLM Classification)
- Sends question to language model with a classification prompt
- LLM determines if question is comparative and extracts product names
- More flexible, maintainable, and language-agnostic
- No hardcoded keywords needed

## How It Works

The `_detect_comparative_question()` method now:

1. **Sends a classification prompt** to the Ollama model with:
   - The user's question
   - Clear examples of comparative vs non-comparative questions
   - Instructions to return JSON response

2. **Parses the JSON response** which includes:
   - `is_comparison`: Boolean indicating if it's a comparison
   - `product1`: First product name (or null)
   - `product2`: Second product name (or null)
   - `reason`: Brief explanation of the classification

3. **Handles edge cases**:
   - Strips markdown code blocks if LLM wraps JSON in backticks
   - Gracefully falls back to non-comparative on parsing errors
   - Uses low temperature (0.1) for deterministic responses

## Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **Flexibility** | Limited to hardcoded patterns | Handles any comparative phrasing |
| **Maintenance** | Must update code for new patterns | Self-learning via LLM |
| **Accuracy** | Regex-based (prone to false negatives) | Semantic understanding via LLM |
| **Examples** | Only works with exact patterns | Works with variations |
| **New languages** | Would need regex for each language | Works across languages |

## Example Questions Handled

The LLM classification now handles:
- "What are Milvus advantages over Pinecone?"
- "How does Milvus compare to Qdrant?"
- "Milvus vs Weaviate"
- "Compare Elasticsearch and Weaviate"
- "What's the difference between Milvus and Pinecone?"
- And any other comparative phrasing

## Performance

- **Cost**: One LLM invocation per question (minimal overhead)
- **Speed**: ~0.5-2 seconds depending on model
- **Temperature**: Low (0.1) for consistent classification
- **Max tokens**: Limited to 200 for fast responses

## Implementation Details

- **File**: `src/agents/strands_rag_agent.py`
- **Method**: `_detect_comparative_question()`
- **Called from**: `answer_question()` after scope checking
- **Returns**: `(is_comparative: bool, (product1: str, product2: str) | None)`

## Integration

The classification integrates seamlessly with the existing pipeline:

```
answer_question()
├── Security attack check
├── Scope checking (in/out of Milvus scope)
├── Comparative question detection [NEW APPROACH]
│   └── if comparative: search_comparison()
│   └── else: standard RAG pipeline
└── Return answer + sources
```
