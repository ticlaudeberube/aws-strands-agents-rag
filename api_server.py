#!/usr/bin/env python3
"""OpenAI-compatible API server for RAG Agent.

Exposes the RAG agent as an OpenAI-compatible API endpoint.
Can be used with Ollama GUI and other compatible clients.

Uses StrandsRAGAgent with MCP support and Strands framework integration.
"""

import logging
import sys
import json
import time
import uvicorn
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.config.settings import get_settings, Settings
from src.agents.strands_rag_agent import StrandsRAGAgent
from src.mcp.mcp_server import RAGAgentMCPServer
from src.tools.tool_registry import get_registry

# Load environment variables from .env file (required for TAVILY_API_KEY and other secrets)
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Pydantic Models
# ============================================================================


class Message(BaseModel):
    """Chat message - Strands Agent standard format with optional timestamp.

    Matches Strands Agent/AgentCore message signature:
    - content: List of ContentBlocks (text, toolUse, toolResult, etc.)
    - timestamp: ISO 8601 for message ordering in AgentCore Memory

    MIGRATION NOTES FOR AGENTCORE:
    - This structure is AgentCore-native and requires NO code changes
    - AgentCore's SessionManager expects exactly this format
    - Timestamp field will be used by AgentCoreMemorySessionManager for chronological ordering
    - Keep this model as-is when migrating to AgentCore (no backwards compatibility needed)

    Example:
    {
        "role": "user",
        "content": [{"text": "What is Milvus?"}],
        "timestamp": "2025-02-28T12:34:56Z"
    }
    """

    role: str
    content: List[
        Dict[str, Any]
    ]  # Strands standard: list of ContentBlocks [{"text": "..."}, {"toolUse": ...}, etc.]
    timestamp: Optional[str] = None  # ISO 8601 format for message ordering


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    messages: List[Message]
    model: Optional[str] = "rag-agent"
    temperature: Optional[float] = 0.1  # Low temperature for factual RAG answers
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = None  # None means use settings.max_tokens
    top_k: Optional[int] = None  # None means use default of 5 for retrieval
    stream: Optional[bool] = False
    force_web_search: Optional[bool] = False  # NEW: Force web search (skip cache)


class ChatCompletionChoice(BaseModel):
    """Chat completion choice."""

    index: int
    message: Message
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: dict


# ============================================================================
# Lifespan Manager
# ============================================================================

# Global state
strands_agent: Optional[StrandsRAGAgent] = None
mcp_server: Optional[RAGAgentMCPServer] = None
settings: Optional[Settings] = None
initialization_error: Optional[str] = None
common_questions: List[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown.

    Initializes:
    - StrandsRAGAgent with all RAG logic, caching, and security
    - MCP Server with registered skills
    """
    global strands_agent, mcp_server, settings, initialization_error, common_questions

    # Startup
    logger.info("=" * 70)
    logger.info("Starting RAG Agent API Server with StrandsRAGAgent")
    logger.info("=" * 70)

    try:
        # Load settings
        settings = get_settings()
        logger.info(f"Settings loaded: {settings.milvus_host}:{settings.milvus_port}")

        # Initialize StrandsRAGAgent
        logger.info("\nInitializing StrandsRAGAgent...")
        strands_agent = StrandsRAGAgent(settings)
        logger.info("✓ StrandsRAGAgent initialized")
        logger.info("  - Multi-layer caching enabled (embedding, search, response cache)")
        logger.info("  - Security attack detection enabled")
        logger.info("  - Scope validation enabled")
        logger.info("  - Semantic response caching enabled")

        # Initialize MCP server and register skills
        logger.info("\nInitializing MCP Server...")
        mcp_server = RAGAgentMCPServer(settings)
        registry = get_registry()

        skills_summary = registry.list_skills()
        logger.info(f"✓ MCP Server initialized with {len(registry.list_tools())} tools")
        logger.info(f"  Skills: {skills_summary}")

        # Load common questions
        try:
            questions_file = Path(__file__).parent / "config" / "common_questions.json"
            if questions_file.exists():
                with open(questions_file, "r") as f:
                    common_questions = json.load(f)
                logger.info(f"✓ Loaded {len(common_questions)} common questions")
        except Exception as e:
            logger.warning(f"Failed to load common questions: {e}")

        # Warm response cache with pre-generated Q&A pairs (if enabled)
        if settings.enable_cache_warmup:
            logger.info("\nWarming response cache with pre-generated Q&A pairs...")
            warm_response_cache(strands_agent, settings)
        else:
            logger.info("\nCache warmup disabled (ENABLE_CACHE_WARMUP=false)")

        logger.info("\n" + "=" * 70)
        logger.info("Server ready! Using StrandsRAGAgent architecture")
        logger.info("=" * 70 + "\n")

        yield

    except Exception as e:
        initialization_error = str(e)
        logger.error(f"✗ Initialization failed: {e}", exc_info=True)
        raise

    finally:
        # Shutdown
        cleanup_resources()


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="RAG Agent API",
    description="OpenAI-compatible API for RAG Agent with MCP Support",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_or_init_agent():
    """Get existing StrandsRAGAgent (assumes it's already initialized on startup)."""
    global strands_agent, settings, initialization_error

    if initialization_error:
        raise HTTPException(status_code=503, detail=initialization_error)

    if strands_agent is None:
        raise HTTPException(
            status_code=503, detail="Agent not initialized. Check server startup logs."
        )

    return strands_agent


def cleanup_resources() -> None:
    """Clean up resources on shutdown."""
    global strands_agent, mcp_server

    logger.info("\n" + "=" * 60)
    logger.info("Shutting down RAG Agent API Server")
    logger.info("=" * 60)

    # Clean up MCP server
    if mcp_server is not None:
        try:
            mcp_server.close()
            logger.info("✓ MCP Server closed")
        except Exception as e:
            logger.warning(f"Error closing MCP Server: {e}")

    # Clean up StrandsRAGAgent (primary agent)
    if strands_agent is not None:
        try:
            strands_agent.close()
            logger.info("✓ StrandsRAGAgent closed")
            logger.info("✓ Milvus connection closed")
            logger.info("✓ Ollama session closed")
        except Exception as e:
            logger.warning(f"Error closing StrandsRAGAgent: {e}")

    logger.info("=" * 60)
    logger.info("✓ Shutdown complete")
    logger.info("=" * 60)


def load_common_questions() -> List[str]:
    """Load common questions from config file for pre-warming cache.

    Returns:
        List of common questions, or empty list if file not found
    """
    try:
        config_path = Path(__file__).parent / "config" / "common_questions.json"
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            questions = data.get("common_questions", [])
            logger.info(f"✓ Loaded {len(questions)} common questions from config")
            return list(questions) if questions else []  # type: ignore[return-value]
    except FileNotFoundError:
        logger.warning(
            "config/common_questions.json not found - cache endpoints will have empty questions list"
        )
        return []
    except Exception as e:
        logger.warning(f"Failed to load common questions: {e}")
        return []


def extract_text_from_content(content: Any) -> str:
    """Extract text from Strands Agent content format.

    Handles both formats:
    - String: "text" (for backward compatibility)
    - Strands ContentBlock list: [{"text": "..."}, {"toolUse": ...}, ...]

    Args:
        content: Message content in any supported format

    Returns:
        Extracted text string
    """
    if isinstance(content, str):
        # Already a string
        return content

    if isinstance(content, list):
        # Strands format: [{"text": "..."}, ...]
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if "text" in block:
                    text_parts.append(str(block["text"]))
        return " ".join(text_parts) if text_parts else ""

    # Fallback
    return str(content)


def warm_response_cache(agent: "StrandsRAGAgent", settings) -> None:
    """Pre-warm response cache with responses from responses.json on startup.

    Automatically loads Q&A pairs from data/responses.json into the response cache
    for semantic matching, as long as the file exists.

    Args:
        agent: StrandsRAGAgent instance with response_cache
        settings: Application settings
    """
    if not agent.response_cache:
        logger.debug("Response cache not available, skipping cache warming")
        return

    try:
        responses_path = Path(__file__).parent / "data" / "responses.json"
        if not responses_path.exists():
            logger.debug(f"responses.json not found at {responses_path}, skipping cache warming")
            return

        with open(responses_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        qa_pairs = data.get("qa_pairs", [])
        if not qa_pairs:
            logger.warning("No Q&A pairs found in responses.json")
            return

        logger.info(f"Warming response cache with {len(qa_pairs)} Q&A pairs from responses.json...")

        skipped = 0
        for qa in qa_pairs:
            question = qa.get("question", "").strip()
            answer = qa.get("answer", "").strip()

            if not question or not answer:
                skipped += 1
                continue

            try:
                # Generate embedding for the question
                question_embedding = agent.ollama_client.embed_text(
                    question,
                    model=settings.ollama_embed_model,
                )

                # Store in response cache
                agent.response_cache.store_response(
                    question=question,
                    question_embedding=question_embedding,
                    response=answer,
                    metadata={
                        "collection": settings.ollama_collection_name,
                        "source": "prewarmed",
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to cache Q&A pair '{question[:50]}': {e}")
                skipped += 1

        cached_count = len(qa_pairs) - skipped
        if cached_count > 0:
            logger.info(f"✓ Response cache warmed with {cached_count} Q&A pairs")
            if skipped > 0:
                logger.info(f"  (Skipped {skipped} invalid pairs)")

    except FileNotFoundError:
        logger.debug("responses.json not found, skipping cache warming")
    except Exception as e:
        logger.warning(f"Failed to warm response cache: {e}")


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/", tags=["info"])
async def root():
    """Root endpoint."""
    return {
        "name": "RAG Agent API",
        "version": "1.0.0",
        "description": "OpenAI-compatible API with MCP support for RAG agent",
        "endpoints": {
            "health": "GET /health",
            "health_detailed": "GET /health/detailed",
            "models": "GET /v1/models",
            "chat": "POST /v1/chat/completions",
            "cache_questions": "GET /api/cache/questions",
            "cache_stats": "GET /api/cache/stats",
            "mcp_server_info": "GET /api/mcp/server/info",
            "mcp_tools": "GET /api/mcp/tools",
            "mcp_skills": "GET /api/mcp/skills",
            "mcp_skill_docs": "GET /api/mcp/skills/{skill_name}",
            "mcp_call_tool": "POST /api/mcp/tools/call",
        },
        "features": {
            "mcp_support": "Enabled (Phase 2)",
            "skill_system": "Enabled (progressive tool disclosure)",
            "auto_cache_warming": "Enabled on startup",
            "semantic_caching": "Enabled (Milvus response cache)",
            "performance": "99.9% speedup on cached queries",
        },
        "architecture": {
            "agent": "StrandsRAGAgent (Phase 2)",
            "mcp_server": "RAGAgentMCPServer",
            "vector_db": "Milvus",
            "llm": "Ollama (local inference)",
        },
    }


@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint."""
    try:
        s = settings if settings else get_settings()
        return {
            "status": "ok",
            "model": "rag-agent",
            "ollama": s.ollama_host,
            "milvus": f"{s.milvus_host}:{s.milvus_port}",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/health/detailed", tags=["health"])
async def health_detailed():
    """Detailed health check for all services."""
    try:
        current_agent = await get_or_init_agent()
        current_settings = settings if settings else get_settings()

        # Check Ollama
        ollama_available = current_agent.ollama_client.is_available()
        ollama_status = "healthy" if ollama_available else "unhealthy"

        # Get Ollama models
        ollama_models = []
        if ollama_available:
            ollama_models = current_agent.ollama_client.get_available_models()

        # Check Milvus
        try:
            milvus_collections = current_agent.vector_db.client.list_collections(
                db_name=current_settings.milvus_db_name
            )
            milvus_status = "healthy"
            milvus_col_count = len(milvus_collections)
        except Exception as e:
            milvus_status = "unhealthy"
            milvus_col_count = 0
            logger.warning(f"Milvus health check failed: {e}")

        return {
            "status": "ok",
            "services": {
                "ollama": {
                    "status": ollama_status,
                    "host": current_settings.ollama_host,
                    "timeout": current_settings.ollama_timeout,
                    "models_available": ollama_models,
                },
                "milvus": {
                    "status": milvus_status,
                    "host": current_settings.milvus_host,
                    "port": current_settings.milvus_port,
                    "database": current_settings.milvus_db_name,
                    "collections": milvus_col_count,
                },
            },
            "caches": {
                "embedding_cache_size": len(current_agent.embedding_cache),
                "search_cache_size": len(current_agent.search_cache),
                "answer_cache_size": len(current_agent.answer_cache),
                "max_cache_size": current_agent.cache_size,
            },
        }
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")


@app.get("/health/ollama", tags=["health"])
async def health_ollama():
    """Health check for Ollama service."""
    try:
        current_agent = await get_or_init_agent()
        current_settings = settings if settings else get_settings()

        available = current_agent.ollama_client.is_available()
        models = current_agent.ollama_client.get_available_models() if available else []

        status = "healthy" if available else "unhealthy"
        return {
            "service": "ollama",
            "status": status,
            "host": current_settings.ollama_host,
            "models": models,
        }
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Ollama health check failed: {str(e)}")


@app.get("/health/milvus", tags=["health"])
async def health_milvus():
    """Health check for Milvus service."""
    try:
        current_agent = await get_or_init_agent()
        current_settings = settings if settings else get_settings()

        collections = current_agent.vector_db.client.list_collections(
            db_name=current_settings.milvus_db_name
        )

        return {
            "service": "milvus",
            "status": "healthy",
            "host": current_settings.milvus_host,
            "port": current_settings.milvus_port,
            "database": current_settings.milvus_db_name,
            "collections": collections,
            "collection_count": len(collections),
        }
    except Exception as e:
        logger.error(f"Milvus health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Milvus health check failed: {str(e)}")


@app.get("/api/cache/questions", tags=["cache"])
async def get_cached_questions():
    """Get list of pre-warmed common questions.

    These questions are cached for instant retrieval (~0ms).
    Useful for chatbot GUI to suggest frequently asked questions.
    """
    return {
        "common_questions": common_questions,
        "count": len(common_questions),
        "description": "Pre-warmed questions cached for instant retrieval",
    }


@app.get("/api/cache/stats", tags=["cache"])
async def get_cache_stats():
    """Get cache statistics and performance metrics."""
    try:
        current_agent = await get_or_init_agent()

        response_cache_stats = {}
        if current_agent.response_cache:
            try:
                response_cache_stats = current_agent.response_cache.get_cache_stats()
            except Exception as e:
                logger.warning(f"Failed to get response cache stats: {e}")

        return {
            "embedding_cache": {
                "size": len(current_agent.embedding_cache),
                "max_size": current_agent.cache_size,
                "utilized": f"{(len(current_agent.embedding_cache) / current_agent.cache_size * 100):.1f}%",
            },
            "search_cache": {
                "size": len(current_agent.search_cache),
                "max_size": current_agent.cache_size,
                "utilized": f"{(len(current_agent.search_cache) / current_agent.cache_size * 100):.1f}%",
            },
            "answer_cache": {
                "size": len(current_agent.answer_cache),
                "max_size": current_agent.cache_size,
                "utilized": f"{(len(current_agent.answer_cache) / current_agent.cache_size * 100):.1f}%",
            },
            "response_cache": response_cache_stats,
            "common_questions_count": len(common_questions),
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MCP Server Endpoints (Phase 2 - Tool Management)
# ============================================================================


@app.get("/api/mcp/server/info", tags=["mcp"])
async def get_mcp_server_info():
    """Get information about the MCP server.

    Returns server metadata, tool count, and available skills.
    """
    global mcp_server

    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP server not initialized")

    try:
        return mcp_server.get_server_info()
    except Exception as e:
        logger.error(f"Failed to get MCP server info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/tools", tags=["mcp"])
async def list_mcp_tools():
    """List all available tools in MCP format.

    Tools are organized by skill category.
    Returns detailed tool definitions with parameters.
    """
    global mcp_server

    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP server not initialized")

    try:
        tools = mcp_server.get_tools()
        return {
            "count": len(tools),
            "tools": tools,
        }
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/skills", tags=["mcp"])
async def list_mcp_skills():
    """List all available skill categories.

    Skills are groups of related tools for progressive tool disclosure.
    """
    global mcp_server

    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP server not initialized")

    try:
        registry = get_registry()
        skills = registry.list_skills()

        return {
            "skills": skills,
            "total_skills": len(skills),
            "total_tools": len(registry.list_tools()),
        }
    except Exception as e:
        logger.error(f"Failed to list MCP skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/skills/{skill_name}", tags=["mcp"])
async def get_mcp_skill_documentation(skill_name: str):
    """Get documentation for a specific skill.

    Returns the full documentation (markdown) for a skill
    including all tools and parameters.

    Args:
        skill_name: Name of the skill (e.g., 'retrieval', 'answer_generation')
    """
    global mcp_server

    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP server not initialized")

    try:
        doc = mcp_server.get_skill_documentation(skill_name)
        return {
            "skill": skill_name,
            "documentation": doc,
        }
    except Exception as e:
        logger.error(f"Failed to get skill documentation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/tools/call", tags=["mcp"])
async def call_mcp_tool(request: dict):
    """Call a tool via MCP interface.

    This endpoint allows direct tool invocation with proper parameter validation.

    Request body:
    {
        "tool": "tool_name",
        "arguments": { "param1": "value1", ... }
    }

    Returns:
        Tool execution result
    """
    global mcp_server

    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP server not initialized")

    try:
        tool_name = request.get("tool")
        arguments = request.get("arguments", {})

        if not tool_name:
            raise ValueError("'tool' field required in request")

        result = await mcp_server.call_tool(tool_name, arguments)

        return {
            "status": "success",
            "tool": tool_name,
            "result": result,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models", tags=["models"])
async def list_models():
    """List available models."""
    return {
        "object": "list",
        "data": [
            {
                "id": "rag-agent",
                "object": "model",
                "owned_by": "aws-strands",
                "permission": [],
            }
        ],
    }


# ============================================================================
# Streaming Helper
# ============================================================================


def _stream_chat_completions(
    agent, settings, request: ChatCompletionRequest, user_message: str, bypass_cache: bool
):
    """Helper function to handle streaming chat completions.

    Returns a StreamingResponse with Server-Sent Events format.
    Uses the agent's async stream_answer() method for true real-time streaming.

    Supports:
    - force_web_search: true → stream_answer_web_search_only()
    - bypass_cache: true → stream_answer_no_cache() (knowledge base only, no web search)
    - Normal: stream_answer()
    """

    async def stream_generator():
        """Generator for streaming response with SSE format."""
        try:
            # Use request parameters or defaults
            retrieval_top_k = request.top_k or 5
            temperature = request.temperature if request.temperature is not None else 0.1
            max_tokens = request.max_tokens or settings.max_tokens
            force_web_search = request.force_web_search or False

            logger.info(f"💾 Streaming response: {user_message[:100]}...")
            logger.info(f"    force_web_search: {force_web_search}, bypass_cache: {bypass_cache}")

            # Use the agent's async streaming method for true real-time response
            # This yields text chunks as they're generated by the LLM
            if force_web_search:
                # 🌐 FORCE WEB SEARCH: Only web search, no knowledge base
                logger.info(f"🌐 [STREAMING] FORCE WEB SEARCH: {user_message[:100]}...")
                async for chunk in agent.stream_answer_web_search_only(
                    question=user_message,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    # All chunks are strings now - wrap in SSE format
                    # Format: data: {json}\n\n
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
            elif bypass_cache:
                # Bypass all caches and query LLM directly (knowledge base only, no web search)
                logger.info(f"[STREAMING_NO_CACHE] Cache bypassed: {user_message[:100]}...")
                async for chunk in agent.stream_answer_no_cache(
                    collection_name=settings.ollama_collection_name,
                    question=user_message,
                    top_k=retrieval_top_k,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
            else:
                # Use normal path with caching
                logger.info(f"[STREAMING] Normal streaming: {user_message[:100]}...")
                async for chunk in agent.stream_answer(
                    collection_name=settings.ollama_collection_name,
                    question=user_message,
                    top_k=retrieval_top_k,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"

            # After streaming completes, send sources as final chunk
            sources = agent._last_stream_sources
            if sources:
                sources_data = {
                    "choices": [
                        {
                            "delta": {"content": ""},  # Empty content to signal end
                        }
                    ],
                    "sources": sources,  # Include sources in this chunk
                }
                yield f"data: {json.dumps(sources_data)}\n\n"

            # Signal successful completion
            yield "data: [STREAM_END]\n\n"

        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@app.post("/v1/chat/completions", tags=["chat"])
async def chat_completions(request: ChatCompletionRequest, bypass_cache: bool = False):
    """OpenAI-compatible chat completions endpoint.

    Accepts full conversation history for context-aware responses.
    Designed for AgentCore compatibility: conversation history can be used
    by the agent for clarification detection and context understanding.

    Supports both streaming and non-streaming responses:
    - stream: false (default) - Returns complete response as JSON
    - stream: true - Returns Server-Sent Events (SSE) stream for real-time chunks

    Query Parameters:
        bypass_cache: Set to true to skip all caches and query LLM directly
                      Example: /v1/chat/completions?bypass_cache=true
    """
    # Track total query time
    total_start_time = time.time()

    try:
        current_agent = await get_or_init_agent()
        current_settings = settings if settings else get_settings()

        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Extract the last user message (current question)
        # Content is in Strands format: [{ text: "..." }] or string
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = extract_text_from_content(msg.content)
                break

        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")

        # Check if streaming is requested
        if request.stream:
            return _stream_chat_completions(
                current_agent,
                current_settings,
                request,
                user_message,
                bypass_cache,
            )

        # Build conversation history (Strands Agent standard format)
        # Preserves full conversation context for future context-aware features
        # Content is already in Strands format: List[ContentBlock]
        #
        # MIGRATION TO AGENTCORE:
        # When integrating AgentCoreMemorySessionManager:
        # 1. The session_manager will auto-load: agent.messages = session_manager.list_messages(session_id)
        # 2. You can DELETE the conversation_history building code below (this block)
        # 3. Keep the ChatCompletionRequest structure - no API changes needed
        # 4. The message format here matches SessionMessage.to_message() output exactly
        # 5. Timestamps will be used for event ordering in AgentCore Memory
        conversation_history = [
            {
                "role": msg.role,
                "content": msg.content,  # Already in Strands format: [{ text: "..."}]
                "timestamp": msg.timestamp,
            }
            for msg in request.messages
        ]

        logger.info(f"Processing {len(conversation_history)} messages in conversation")
        if bypass_cache:
            logger.info(f"Query (CACHE BYPASSED): {user_message[:100]}...")
        else:
            logger.info(f"Query: {user_message[:100]}...")

        # Use request parameters or defaults
        retrieval_top_k = request.top_k or 5
        temperature = request.temperature if request.temperature is not None else 0.1
        max_tokens = request.max_tokens or current_settings.max_tokens
        force_web_search = request.force_web_search or False

        # DIAGNOSTIC LOGGING
        logger.info("[CHAT_ENDPOINT] Request received:")
        logger.info(f"[CHAT_ENDPOINT] - User message: {user_message[:100]}...")
        logger.info(
            f"[CHAT_ENDPOINT] - force_web_search: {force_web_search} (type: {type(force_web_search)})"
        )
        logger.info(f"[CHAT_ENDPOINT] - bypass_cache: {bypass_cache}")
        logger.info(f"[CHAT_ENDPOINT] - temperature: {temperature}, max_tokens: {max_tokens}")

        timing_data = {}
        try:
            if force_web_search:
                # 🌐 FORCE WEB SEARCH: Only web search, no knowledge base
                logger.info(
                    f"🌐 [CHAT_ENDPOINT] FORCE WEB SEARCH SELECTED: {user_message[:100]}..."
                )
                answer, sources = current_agent.answer_question_web_search_only(
                    question=user_message,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                logger.info(
                    f"[CHAT_ENDPOINT] Web search response: {len(sources)} sources, {len(answer)} chars"
                )
            elif bypass_cache:
                # Bypass all caches and query LLM directly (knowledge base only, no web search)
                answer, sources = current_agent.answer_question_no_cache(
                    collection_name=current_settings.ollama_collection_name,
                    question=user_message,
                    top_k=retrieval_top_k,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                # Use normal path with caching
                answer, sources = current_agent.answer_question(
                    collection_name=current_settings.ollama_collection_name,
                    question=user_message,
                    top_k=retrieval_top_k,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
        except Exception as e:
            logger.error(f"RAG error: {e}")
            answer = f"Error: {str(e)}"
            sources = []

        # Deduplicate sources by document_name or text to avoid showing the same document multiple times
        logger.info(
            f"[API_RESPONSE] Before deduplication: {len(sources) if sources else 0} sources"
        )
        logger.info(f"[API_RESPONSE] sources value: {sources}")

        if sources:
            seen = set()
            unique_sources = []
            for source in sources:
                # For web search sources, use URL as key
                # For knowledge base sources, use document_name or text
                if source.get("source_type") == "web_search":
                    key = source.get("url", "")
                else:
                    key = source.get("document_name") or source.get("text", "")

                if key and key not in seen:
                    seen.add(key)
                    unique_sources.append(source)
            sources = unique_sources
            logger.info(f"[API_RESPONSE] After deduplication: {len(sources)} sources")

        # Calculate total query time
        total_time = time.time() - total_start_time
        timing_data["total_time_ms"] = round(total_time * 1000, 2)

        return {
            "id": f"chatcmpl-{datetime.now().timestamp()}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model or "rag-agent",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(user_message.split()),
                "completion_tokens": len(answer.split()),
                "total_tokens": len(user_message.split()) + len(answer.split()),
            },
            "sources": sources,  # Include sources in response (deduplicated)
            "timing": timing_data,  # Include timing metrics
        }
    except Exception as e:
        logger.error(f"Chat completions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions/stream", tags=["chat"])
async def chat_completions_stream(request: ChatCompletionRequest):
    """Stream chat completions endpoint for real-time response streaming.

    Accepts full conversation history for AgentCore-compatible context awareness.
    Returns Server-Sent Events (SSE) stream with answer chunks as they are generated.
    This provides a perceived immediate response while the full answer is being
    generated in the background.

    The stream yields chunks in the format: data: {chunk}\n\n
    Client can consume with JavaScript fetch() and EventSource API.

    MIGRATION NOTES FOR AGENTCORE:
    - Same message handling as non-streaming endpoint
    - Timestamp field is preserved in the request
    - This endpoint signature is fully AgentCore-compatible
    - When integrating AgentCore Runtime, the request contract stays the same
    - No API signature changes needed for migration
    """
    try:
        current_agent = await get_or_init_agent()
        current_settings = settings if settings else get_settings()

        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Extract the last user message (current question)
        # Content is in Strands format: [{ text: "..." }] or string
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = extract_text_from_content(msg.content)
                break

        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")

        # Build conversation history (Strands Agent standard format)
        # MIGRATION NOTE: Same as non-streaming endpoint
        # When integrating AgentCore, delete this conversation_history building block
        # AgentCore's SessionManager will auto-load: agent.messages = session_manager.list_messages(...)
        conversation_history = [
            {
                "role": msg.role,
                "content": msg.content,  # Already in Strands format: [{ text: "..."}]
                "timestamp": msg.timestamp,
            }
            for msg in request.messages
        ]

        logger.info(
            f"Stream Query: {user_message[:100]}... (conversation history: {len(conversation_history)} messages)"
        )

        # Use request parameters or defaults
        retrieval_top_k = request.top_k or 5
        temperature = request.temperature if request.temperature is not None else 0.1
        max_tokens = request.max_tokens or current_settings.max_tokens
        force_web_search = request.force_web_search or False
        bypass_cache = (
            False  # Check if this is a cache bypass request (from query params or header)
        )

        async def stream_generator():
            """Generator for streaming response with SSE format."""
            try:
                # Choose the appropriate streaming method based on query type
                if force_web_search:
                    # 🌐 FORCE WEB SEARCH: Only web search, no knowledge base
                    logger.info(f"🌐 STREAMING FORCE WEB SEARCH: {user_message[:100]}...")
                    async for chunk in current_agent.stream_answer_web_search_only(
                        question=user_message,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
                elif bypass_cache:
                    # Bypass all caches and query LLM directly (with knowledge base + web search)
                    logger.info(f"[STREAM_NO_CACHE] Cache bypassed: {user_message[:100]}...")
                    async for chunk in current_agent.stream_answer_no_cache(
                        collection_name=current_settings.ollama_collection_name,
                        question=user_message,
                        top_k=retrieval_top_k,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
                else:
                    # Use normal path with caching
                    logger.info(f"[STREAM] Normal streaming: {user_message[:100]}...")
                    async for chunk in current_agent.stream_answer(
                        collection_name=current_settings.ollama_collection_name,
                        question=user_message,
                        top_k=retrieval_top_k,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"

                # After streaming completes, send sources as final chunk
                sources = current_agent._last_stream_sources
                if sources:
                    sources_data = {
                        "choices": [
                            {
                                "delta": {"content": ""},  # Empty content to signal end
                            }
                        ],
                        "sources": sources,  # Include sources in this chunk
                    }
                    yield f"data: {json.dumps(sources_data)}\n\n"

                # Signal end of stream
                yield "data: [STREAM_END]\n\n"
            except Exception as e:
                logger.error(f"Stream generation error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Stream endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/cache/clear", tags=["cache"])
async def clear_cache():
    """Clear all RAG Agent caches.

    Clears:
    - Embedding cache (query embeddings)
    - Search cache (retrieval results)
    - response cache (generated answers)
    - Response cache (semantic matching cache)

    Returns immediately without waiting for dependent operations.
    """
    current_agent = await get_or_init_agent()
    if not current_agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        logger.info("Cache clear request received")

        # Clear caches in the running agent
        current_agent.clear_caches()

        logger.info("✓ All caches cleared successfully")

        return {
            "status": "success",
            "message": "All caches cleared",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error clearing caches: {e}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


def main():
    """Start the API server with lifespan context manager handling initialization."""
    global settings, initialization_error, common_questions

    logger.info("=" * 70)
    logger.info("RAG Agent API Server Starting")
    logger.info("=" * 70)

    settings = get_settings()
    logger.info(f"Server: http://0.0.0.0:{settings.api_port}")
    logger.info(f"Docs: http://localhost:{settings.api_port}/docs")
    logger.info("Press Ctrl+C to shutdown gracefully")
    logger.info("=" * 70)

    try:
        # Load common questions for cache endpoints
        logger.info("Loading common questions...")
        common_questions = load_common_questions()

        logger.info("=" * 70)
        logger.info("Server Ready - Accepting Requests")
        logger.info("=" * 70 + "\n")

        # Run uvicorn server with lifespan context manager
        # Initialization and cleanup handled by lifespan context manager
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=settings.api_port,
            log_level="info",
            # Graceful shutdown timeout (allows running requests to complete)
            timeout_graceful_shutdown=15,
            # Allow port reuse immediately after shutdown
            loop="auto",
        )
    except KeyboardInterrupt:
        logger.info("\n✓ Server interrupted by user")
        cleanup_resources()
    except Exception as e:
        logger.error(f"Server startup failed: {e}")
        cleanup_resources()
        sys.exit(1)


if __name__ == "__main__":
    main()
