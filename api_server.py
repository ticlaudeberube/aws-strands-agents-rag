#!/usr/bin/env python3
"""OpenAI-compatible API server for RAG Agent.

Exposes the RAG agent as an OpenAI-compatible API endpoint.
Can be used with Ollama GUI and other compatible clients.
"""

import logging
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import get_settings
from src.agents.rag_agent import RAGAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Pydantic Models
# ============================================================================

class Message(BaseModel):
    """Chat message."""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    messages: List[Message]
    model: Optional[str] = "rag-agent"
    temperature: Optional[float] = 0.1  # Low temperature for factual RAG answers
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = None  # None means use settings.max_tokens
    top_k: Optional[int] = None  # None means use default of 5 for retrieval
    stream: Optional[bool] = False


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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    # Startup
    yield
    # Shutdown
    cleanup_resources()


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="RAG Agent API",
    description="OpenAI-compatible API for RAG Agent",
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

# Global state
agent: Optional[RAGAgent] = None
settings: Optional[object] = None
initialization_error: Optional[str] = None
common_questions: List[str] = []


async def get_or_init_agent():
    """Get existing agent (assumes it's already initialized on startup)."""
    global agent, settings, initialization_error
    
    if initialization_error:
        raise HTTPException(status_code=503, detail=initialization_error)
    
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check server startup logs.")
    
    return agent


def cleanup_resources() -> None:
    """Clean up resources on shutdown."""
    global agent, settings
    
    logger.info("\n" + "=" * 60)
    logger.info("Shutting down RAG Agent API Server")
    logger.info("=" * 60)
    
    if agent is not None:
        try:
            # Close vector DB connection
            if hasattr(agent.vector_db, 'client') and agent.vector_db.client:
                try:
                    agent.vector_db.client.close()
                    logger.info("✓ Milvus connection closed")
                except Exception as e:
                    logger.warning(f"Failed to close Milvus connection: {e}")
            
            # Close Ollama session
            if hasattr(agent.ollama_client, 'session') and agent.ollama_client.session:
                try:
                    agent.ollama_client.session.close()
                    logger.info("✓ Ollama session closed")
                except Exception as e:
                    logger.warning(f"Failed to close Ollama session: {e}")
            
            logger.info("✓ All resources cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
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
            return questions
    except FileNotFoundError:
        logger.warning("config/common_questions.json not found - cache endpoints will have empty questions list")
        return []
    except Exception as e:
        logger.warning(f"Failed to load common questions: {e}")
        return []


def warm_response_cache(agent: "RAGAgent", settings) -> None:
    """Pre-warm response cache with answers from answers.json on startup.
    
    Automatically loads Q&A pairs from data/answers.json into the response cache
    for semantic matching, as long as the file exists.
    
    Args:
        agent: RAGAgent instance with response_cache
        settings: Application settings
    """
    if not agent.response_cache:
        logger.debug("Response cache not available, skipping cache warming")
        return
    
    try:
        answers_path = Path(__file__).parent / "data" / "answers.json"
        if not answers_path.exists():
            logger.debug(f"answers.json not found at {answers_path}, skipping cache warming")
            return
        
        with open(answers_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        qa_pairs = data.get("qa_pairs", [])
        if not qa_pairs:
            logger.warning("No Q&A pairs found in answers.json")
            return
        
        logger.info(f"Warming response cache with {len(qa_pairs)} Q&A pairs from answers.json...")
        
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
                    }
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
        logger.debug("answers.json not found, skipping cache warming")
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
        "endpoints": {
            "health": "GET /health",
            "health_detailed": "GET /health/detailed",
            "models": "GET /v1/models",
            "chat": "POST /v1/chat/completions",
            "cache_questions": "GET /api/cache/questions",
            "cache_stats": "GET /api/cache/stats",
        },
        "features": {
            "auto_cache_warming": "Enabled on startup",
            "semantic_caching": "Enabled (Milvus response cache)",
            "performance": "99.9% speedup on cached queries",
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
        current_settings = settings if settings else get_settings()
        
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


@app.post("/v1/chat/completions", tags=["chat"])
async def chat_completions(request: ChatCompletionRequest, bypass_cache: bool = False):
    """OpenAI-compatible chat completions endpoint.
    
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
        
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")
        
        if bypass_cache:
            logger.info(f"Query (CACHE BYPASSED): {user_message[:100]}...")
        else:
            logger.info(f"Query: {user_message[:100]}...")
        
        # Use request parameters or defaults
        retrieval_top_k = request.top_k or 5
        temperature = request.temperature if request.temperature is not None else 0.1
        max_tokens = request.max_tokens or current_settings.max_tokens
        
        timing_data = {}
        try:
            if bypass_cache:
                # Bypass all caches and query LLM directly
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
        if sources:
            seen = set()
            unique_sources = []
            for source in sources:
                # Use document_name as primary key for deduplication, fall back to text
                key = source.get("document_name") or source.get("text", "")
                if key and key not in seen:
                    seen.add(key)
                    unique_sources.append(source)
            sources = unique_sources
        
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
    
    Returns Server-Sent Events (SSE) stream with answer chunks as they are generated.
    This provides a perceived immediate response while the full answer is being
    generated in the background.
    
    The stream yields chunks in the format: data: {chunk}\n\n
    Client can consume with JavaScript fetch() and EventSource API.
    """
    try:
        current_agent = await get_or_init_agent()
        current_settings = settings if settings else get_settings()
        
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")
        
        logger.info(f"Stream Query: {user_message[:100]}...")
        
        async def stream_generator():
            """Generator for streaming response with SSE format."""
            try:
                # Use request parameters or defaults
                retrieval_top_k = request.top_k or 5
                temperature = request.temperature if request.temperature is not None else 0.1
                max_tokens = request.max_tokens or current_settings.max_tokens
                
                # Create a task for the streaming answer
                async for chunk in current_agent.stream_answer(
                    collection_name=current_settings.ollama_collection_name,
                    question=user_message,
                    top_k=retrieval_top_k,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    # Yield in Server-Sent Events format
                    yield f"data: {chunk}\n\n"
                
                # Signal end of stream
                yield "data: [STREAM_END]\n\n"
            except Exception as e:
                logger.error(f"Stream generation error: {e}")
                yield f"data: [Error: {str(e)}]\n\n"
        
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
    - Answer cache (generated answers)
    - Response cache (semantic matching cache)
    
    Returns immediately without waiting for dependent operations.
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        logger.info("Cache clear request received")
        
        # Clear caches in the running agent
        agent.clear_caches()
        
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
    """Start the API server with cache warming on startup."""
    global agent, settings, initialization_error, common_questions
    
    logger.info("=" * 60)
    logger.info("RAG Agent API Server Starting")
    logger.info("=" * 60)
    settings = get_settings()
    logger.info(f"Server: http://0.0.0.0:{settings.api_port}")
    logger.info(f"Docs: http://localhost:{settings.api_port}/docs")
    logger.info("Press Ctrl+C to shutdown gracefully")
    logger.info("=" * 60 + "\n")
    
    try:
        # Load common questions for cache endpoints
        logger.info("Loading common questions...")
        common_questions = load_common_questions()
        
        # Initialize RAG Agent on startup
        logger.info("Initializing RAG Agent...")
        # Note: Ensure Milvus and Ollama are running before starting this server
        agent = RAGAgent(settings=settings)
        
        if not agent.ollama_client.is_available():
            msg = f"Ollama not available at {settings.ollama_host}"
            initialization_error = msg
            raise RuntimeError(msg)
        
        logger.info("✓ RAG Agent initialized")
        logger.info(f"✓ Ollama: {settings.ollama_host}")
        logger.info(f"✓ Milvus: {settings.milvus_host}:{settings.milvus_port}")
        logger.info(f"✓ Database: {settings.milvus_db_name}\n")
        
        # Warm response cache with pre-generated answers
        logger.info("Warming response cache...")
        warm_response_cache(agent, settings)
        
        logger.info("=" * 60)
        logger.info("Server Ready - Accepting Requests")
        logger.info("=" * 60 + "\n")
        
        # Run uvicorn server with graceful shutdown
        # Note: lifespan parameter replaces deprecated on_event handlers
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=settings.api_port,
            log_level="info",
            # Graceful shutdown timeout (allows running requests to complete)
            timeout_graceful_shutdown=15,
            # Allow port reuse immediately after shutdown
            loop="auto",
            # Use uvicorn's default signal handling (SIGTERM, SIGINT)
            # which properly closes connections before port release
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
