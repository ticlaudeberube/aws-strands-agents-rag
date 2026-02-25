#!/usr/bin/env python3
"""OpenAI-compatible API server for RAG Agent.

Exposes the RAG agent as an OpenAI-compatible API endpoint.
Can be used with Ollama GUI and other compatible clients.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = None
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
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="RAG Agent API",
    description="OpenAI-compatible API for RAG Agent",
    version="1.0.0",
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


async def get_or_init_agent():
    """Lazy initialize agent on first request."""
    global agent, settings, initialization_error
    
    if initialization_error:
        raise HTTPException(status_code=503, detail=initialization_error)
    
    if agent is not None:
        return agent
    
    try:
        logger.info("Initializing RAG Agent...")
        settings = get_settings()
        agent = RAGAgent(settings=settings)
        
        if not agent.ollama_client.is_available():
            msg = f"Ollama not available at {settings.ollama_host}"
            initialization_error = msg
            raise RuntimeError(msg)
        
        logger.info("✓ RAG Agent initialized")
        logger.info(f"✓ Ollama: {settings.ollama_host}")
        logger.info(f"✓ Milvus: {settings.milvus_host}:{settings.milvus_port}")
        logger.info(f"✓ Database: {settings.milvus_db_name}")
        return agent
        
    except Exception as e:
        initialization_error = str(e)
        logger.error(f"Agent init failed: {e}")
        raise HTTPException(status_code=503, detail=initialization_error)


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
            "models": "GET /v1/models",
            "chat": "POST /v1/chat/completions",
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
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint."""
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
        
        logger.info(f"Query: {user_message[:100]}...")
        
        try:
            answer = current_agent.answer_question(
                collection_name=current_settings.ollama_collection_name,
                question=user_message,
                top_k=5,
            )
        except Exception as e:
            logger.error(f"RAG error: {e}")
            answer = f"Error: {str(e)}"
        
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
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", tags=["chat"])
async def chat(request: ChatCompletionRequest):
    """Chat endpoint (alias)."""
    return await chat_completions(request)


# ============================================================================
# Main
# ============================================================================

def main():
    """Start the API server."""
    logger.info("=" * 60)
    logger.info("RAG Agent API Server Starting")
    logger.info("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
