# Production Readiness Gaps & Missing Features

**Status**: Critical gaps identified. This document outlines missing production-ready features needed before deploying to production with AgentCore or Ollama locally.

**Objective Alignment**:
- ✅ Local Ollama integration mostly complete
- ⚠️ AgentCore production readiness needs work
- ❌ Several critical production features missing

---

## 🔴 CRITICAL GAPS (Must Fix Before Production)

### 1. **Configuration Validation on Startup**
**Status**: ❌ NOT IMPLEMENTED

Configuration validity is not checked when the application starts. This can lead to runtime failures after deployment.

**Impact**:
- AgentCore mode enabled but Redis not available → fails at first request
- Invalid model names → crashes during inference
- Missing API keys (TAVILY_API_KEY) → feature silently fails

**What's Needed**:
```python
# src/config/startup_validation.py
def validate_startup_config(settings: Settings) -> List[str]:
    """Validate configuration on startup. Return list of errors."""
    errors = []

    # AgentCore validation
    if settings.use_agentcore:
        if not settings.redis_cache_enabled and not settings.use_dynamodb_cache:
            errors.append("AgentCore mode requires REDIS_CACHE_ENABLED or USE_DYNAMODB_CACHE")
        if settings.redis_cache_enabled and not settings.redis_host:
            errors.append("REDIS_CACHE_ENABLED=true but REDIS_HOST not configured")

    # Model validation
    if settings.ollama_model not in available_models:
        errors.append(f"OLLAMA_MODEL '{settings.ollama_model}' not found in Ollama")

    # Message length validation
    if settings.min_message_length >= settings.max_message_length:
        errors.append(f"MIN_MESSAGE_LENGTH ({settings.min_message_length}) >= MAX_MESSAGE_LENGTH ({settings.max_message_length})")

    # Web search validation
    if settings.enable_web_search_supplement and not settings.tavily_api_key:
        errors.append("Web search enabled but TAVILY_API_KEY not configured")

    return errors

# Usage in api_server.py startup
config_errors = validate_startup_config(settings)
if config_errors:
    for error in config_errors:
        logger.error(f"Configuration Error: {error}")
    sys.exit(1)
```

**Files to Update**:
- Create `src/config/startup_validation.py`
- Update `api_server.py` lifespan manager to call validation

---

### 2. **Request Size Limiting**
**Status**: ❌ NOT IMPLEMENTED

API accepts unlimited request sizes, vulnerable to DoS attacks and memory exhaustion.

**Impact**:
- Large request bodies can exhaust memory
- Streaming responses can be exploited
- No protection against malicious file uploads

**What's Needed**:
```python
# In api_server.py, add middleware
from fastapi.middleware import Middleware
from fastapi.exceptions import RequestValidationError

# Configure request size limits
MAX_REQUEST_SIZE = 1_000_000  # 1MB
MAX_RESPONSE_SIZE = 50_000_000  # 50MB for streaming

# Add middleware before creating app
middleware = [
    Middleware(
        RequestSizeLimitMiddleware,
        max_request_size=MAX_REQUEST_SIZE,
    ),
]

app = FastAPI(
    middleware=middleware,
    ...
)

# Custom middleware
class RequestSizeLimitMiddleware:
    def __init__(self, app, max_request_size):
        self.app = app
        self.max_request_size = max_request_size

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        received_size = 0

        async def receive_wrapper():
            nonlocal received_size
            message = await receive()
            if 'body' in message:
                received_size += len(message['body'])
                if received_size > self.max_request_size:
                    raise RequestValidationError(
                        f"Request body too large: {received_size} > {self.max_request_size}"
                    )
            return message

        await self.app(scope, receive_wrapper, send)
```

**Also requires**:
- Configuration in `.env.example`: `MAX_REQUEST_SIZE=1000000`
- Add to `Settings`: `max_request_size` field

---

### 3. **Security Headers**
**Status**: ⚠️ PARTIALLY IMPLEMENTED

CORS is configured but missing critical security headers.

**What's Missing**:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000`
- `Content-Security-Policy`

**What's Needed**:
```python
# Add to api_server.py before creating app
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,  # Configure in .env
)

# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # HSTS (only if using HTTPS)
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # CSP
    response.headers["Content-Security-Policy"] = "default-src 'self'"

    return response
```

---

### 4. **Request ID / Correlation ID Tracking**
**Status**: ❌ NOT IMPLEMENTED

No request tracing across services. Makes debugging production issues very difficult.

**Impact**:
- Can't trace requests through Ollama, Milvus, Redis, etc.
- Difficult to debug production issues
- Poor observability for distributed tracing

**What's Needed**:
```python
# src/middleware/request_id.py
import uuid
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in context
        request.state.request_id = request_id

        # Log with request ID
        logger.info(f"[{request_id}] {request.method} {request.url.path}")

        response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-ID"] = request_id

        return response

# In api_server.py
app.add_middleware(RequestIDMiddleware)

# Usage in logger
logger.info(f"[{request.state.request_id}] Processing query", extra={
    "request_id": request.state.request_id,
    "timestamp": datetime.utcnow(),
})

# Pass to external services
headers = {
    "X-Request-ID": request.state.request_id,
    "X-Correlation-ID": request.state.request_id,
}
ollama_response = ollama_client.embed(text, headers=headers)
```

**Also requires**:
- Update logging to include request_id
- Pass request_id to Ollama, Milvus, Redis clients
- Document correlation ID propagation in API docs

---

### 5. **Rate Limiting**
**Status**: ❌ NOT IMPLEMENTED

No rate limiting. Vulnerable to abuse and DoS attacks.

**Impact**:
- Anyone can spam the API
- No cost control for web search or LLM calls
- No protection against single-user causing DoS

**What's Needed**:
```python
# pip install slowapi

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply rate limiting to endpoints
@app.post("/v1/chat/completions")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def chat_completions(request: ChatCompletionRequest):
    ...

@app.get("/health")
@limiter.limit("100/minute")  # Higher limit for health checks
async def health():
    ...
```

**Configuration Needed**:
```bash
# .env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_CHAT_COMPLETIONS="10/minute"
RATE_LIMIT_HEALTH="100/minute"
RATE_LIMIT_STORAGE="5/hour"  # Cache operations (expensive)
RATE_LIMIT_BY="remote_address"  # or "user_id" if auth implemented
```

---

### 6. **Database Initialization & Migrations**
**Status**: ⚠️ PARTIAL

Milvus collections are created on-demand but no schema versioning or migration system.

**Impact**:
- No way to upgrade schema without manual intervention
- Multiple instances might create collections simultaneously
- No rollback mechanism for schema changes

**What's Needed**:
```python
# src/db/migrations.py
from alembic import __version__ as alembic_version
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

class MilvusSchemaManager:
    """Manages Milvus schema versions and migrations"""

    def __init__(self, milvus_client: MilvusClient):
        self.client = milvus_client
        self.schema_version = 1

    def init_schema(self) -> bool:
        """Initialize schema on first run. Returns True if initialized."""
        # Create system collection to track schema version
        if not self.client.has_collection("_schema_versions"):
            self.client.create_collection(
                collection_name="_schema_versions",
                schema=self._get_schema_version_schema(),
            )

        # Check current version
        result = self.client.query(
            collection_name="_schema_versions",
            filter="",
            limit=1
            output_fields=["version", "timestamp"],
        )

        if not result:
            # First run - initialize all collections
            self._create_rag_collection()
            self._create_cache_collection()

            # Record schema version
            self.client.insert(
                collection_name="_schema_versions",
                data=[{
                    "version": self.schema_version,
                    "timestamp": datetime.utcnow().isoformat(),
                }]
            )
            logger.info(f"Schema initialized at version {self.schema_version}")
            return True

        # Check if migration needed
        current_version = result[0]["version"]
        if current_version < self.schema_version:
            self._run_migrations(current_version, self.schema_version)

        return False

    def _run_migrations(self, from_version: int, to_version: int):
        """Run migrations from old version to new version"""
        logger.info(f"Running migrations from v{from_version} to v{to_version}")

        if from_version == 1 and to_version == 2:
            # Example: Add new field to existing collection
            self._add_collection_field(
                collection_name="milvus_rag_collection",
                field_name="source_url",
                field_type=DataType.VARCHAR,
            )

        # Update version
        self.client.update(
            collection_name="_schema_versions",
            data=[{"version": to_version, "timestamp": datetime.utcnow()}],
        )
```

**Usage in api_server.py**:
```python
schema_manager = MilvusSchemaManager(milvus_client)
is_first_init = schema_manager.init_schema()

if is_first_init:
    logger.info("Database initialized successfully")
else:
    logger.info("Database schema is current")
```

---

## 🟡 HIGH PRIORITY GAPS (Should Fix Before Production)

### 7. **Authentication & API Keys**
**Status**: ❌ NOT IMPLEMENTED

API has no authentication. Anyone can call it.

**What's Needed**:
```python
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi import Depends, HTTPException

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthCredentials = Depends(security)):
    api_key = credentials.credentials

    # Validate against configured API keys
    if api_key not in settings.valid_api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return api_key

# Apply to protected endpoints
@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key),
):
    ...
```

**Configuration**:
```bash
# .env
API_KEY_REQUIRED=true
VALID_API_KEYS=["sk-...", "sk-..."]  # JSON array of valid keys
```

---

### 8. **CORS Configuration - Security**
**Status**: ⚠️ PARTIALLY IMPLEMENTED

Currently using `allow_origins=["*"]` which is insecure. Should be restricted.

**What's Needed**:
```python
# Update CORS configuration
allowed_origins = settings.allowed_origins.split(",") if settings.use_agentcore else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # List of specific origins
    allow_credentials=True,
    allow_methods=["POST", "GET"],  # Only needed methods
    allow_headers=["Content-Type", "Authorization"],  # Only needed headers
    expose_headers=["X-Request-ID"],
    max_age=3600,
)
```

**Configuration**:
```bash
# .env - For production
ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
```

---

### 9. **Graceful Shutdown & Cleanup**
**Status**: ⚠️ PARTIALLY IMPLEMENTED

Shutdown handler exists but may not properly close all connections.

**What's Needed**:
```python
# Ensure all clients are properly closed
async def shutdown():
    logger.info("Shutting down gracefully...")

    # Close database connections
    if hasattr(strands_agent, 'vector_db'):
        strands_agent.vector_db.client.close()

    # Close HTTP sessions
    if hasattr(strands_agent, 'http_session'):
        await strands_agent.http_session.close()

    # Close MCP server
    if mcp_server:
        await mcp_server.shutdown()

    # Wait for in-flight requests (already handled by uvicorn timeout)
    await asyncio.sleep(1)

    logger.info("Shutdown complete")

# In lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await startup()
    yield
    # Shutdown
    await shutdown()
```

---

### 10. **Error Response Standardization**
**Status**: ⚠️ DOCUMENTED BUT NOT FULLY IMPLEMENTED

GlobalErrorResponse is documented in ERROR_HANDLING.md but not fully integrated.

**What's Needed** (See ERROR_HANDLING.md for full spec):
- Implement `GlobalErrorResponse` Pydantic model
- Add error factory functions
- Update all endpoints to return structured errors
- Handle both synchronous and streaming endpoints

**Files to Create**:
```python
# src/api/error_responses.py
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Any

class ErrorCode(str, Enum):
    # Validation errors
    VALIDATION_EMPTY = "VALIDATION_EMPTY"
    VALIDATION_MIN_LENGTH = "VALIDATION_MIN_LENGTH"
    VALIDATION_MAX_LENGTH = "VALIDATION_MAX_LENGTH"
    VALIDATION_SUSPICIOUS_PATTERN = "VALIDATION_SUSPICIOUS_PATTERN"
    VALIDATION_EXCESSIVE_REPETITION = "VALIDATION_EXCESSIVE_REPETITION"

    # Security errors
    SECURITY_SCRIPT_INJECTION = "SECURITY_SCRIPT_INJECTION"
    SECURITY_JAVASCRIPT_PROTOCOL = "SECURITY_JAVASCRIPT_PROTOCOL"
    SECURITY_EVENT_HANDLER = "SECURITY_EVENT_HANDLER"
    SECURITY_IFRAME_INJECTION = "SECURITY_IFRAME_INJECTION"
    SECURITY_MALICIOUS_INTENT = "SECURITY_MALICIOUS_INTENT"

    # Service errors
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVICE_AGENT_NOT_INITIALIZED = "SERVICE_AGENT_NOT_INITIALIZED"
    SERVICE_MILVUS_UNAVAILABLE = "SERVICE_MILVUS_UNAVAILABLE"
    SERVICE_OLLAMA_UNAVAILABLE = "SERVICE_OLLAMA_UNAVAILABLE"

    # System errors
    SYSTEM_INTERNAL_ERROR = "SYSTEM_INTERNAL_ERROR"

class ValidationErrorDetail(BaseModel):
    field: str
    constraint: str
    constraint_value: str
    value_received: Optional[Any] = None

class GlobalErrorResponse(BaseModel):
    error: bool = True
    error_code: ErrorCode
    category: str  # validation_error, security_error, service_error, system_error
    message: str
    details: Optional[List[ValidationErrorDetail]] = None
    suggestion: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    request_id: Optional[str] = None

def create_validation_error(
    error_code: ErrorCode,
    message: str,
    suggestion: str = None,
    field: str = None,
    constraint: str = None,
    constraint_value: str = None,
    value_received: Any = None,
) -> GlobalErrorResponse:
    """Factory function for validation errors"""
    return GlobalErrorResponse(
        error_code=error_code,
        category="validation_error",
        message=message,
        suggestion=suggestion,
        details=[
            ValidationErrorDetail(
                field=field,
                constraint=constraint,
                constraint_value=constraint_value,
                value_received=value_received,
            )
        ] if field else None,
    )
```

---

## 🟡 MEDIUM PRIORITY GAPS

### 11. **Circuit Breaker for External Services**
**Status**: ⚠️ Retry logic exists, but no circuit breaker

No circuit breaker pattern for Ollama, Milvus, or Tavily when they're down.

**What's Needed**:
```python
from pybreaker import CircuitBreaker

# Initialize circuit breakers for each external service
ollama_cb = CircuitBreaker(
    name="ollama",
    fail_max=5,  # Fail after 5 consecutive errors
    reset_timeout=60,  # Reset after 60 seconds
)

milvus_cb = CircuitBreaker(
    name="milvus",
    fail_max=5,
    reset_timeout=60,
)

tavily_cb = CircuitBreaker(
    name="tavily",
    fail_max=3,  # More aggressive for third-party
    reset_timeout=300,  # Longer reset
)

# Wrap service calls
@ollama_cb
def ollama_embed(text):
    return ollama_client.embed(text)

# Handle circuit breaker open
try:
    embedding = ollama_embed(query)
except CircuitBreakerListener.CircuitBreakerOpenException:
    raise HTTPException(
        status_code=503,
        detail=GlobalErrorResponse(
            error_code=ErrorCode.SERVICE_OLLAMA_UNAVAILABLE,
            message="Ollama service temporarily unavailable",
            suggestion="Please try again in a few moments",
        ).model_dump()
    )
```

---

### 12. **Structured Logging with Correlation ID**
**Status**: ⚠️ Basic logging exists, no structured logging format

Current logging doesn't include correlation IDs or structured format for log aggregation.

**What's Needed**:
```python
# Use JSON structured logging (see ERROR_HANDLING.md for logging_config.py)
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()

# Usage with correlation ID
log.info("processing_query", query_id=request.state.request_id, model="qwen2.5")
```

---

### 13. **Health Check - Dependencies**
**Status**: ⚠️ Basic health checks exist but could be more comprehensive

Current health checks don't validate all critical dependencies.

**What's Needed**:
```python
@app.get("/health", tags=["health"])
async def full_health_check():
    """Comprehensive health check for all dependencies"""

    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "dependencies": {}
    }

    # Check Ollama
    try:
        ollama_status = ollama_client.version()
        health["dependencies"]["ollama"] = {
            "status": "healthy",
            "version": ollama_status,
        }
    except Exception as e:
        health["dependencies"]["ollama"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health["status"] = "degraded"

    # Check Milvus
    try:
        collections = milvus_client.list_collections()
        health["dependencies"]["milvus"] = {
            "status": "healthy",
            "collections": len(collections),
        }
    except Exception as e:
        health["dependencies"]["milvus"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health["status"] = "degraded"

    # Check Redis (if AgentCore)
    if settings.use_agentcore and settings.redis_cache_enabled:
        try:
            redis_client.ping()
            health["dependencies"]["redis"] = {"status": "healthy"}
        except Exception as e:
            health["dependencies"]["redis"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            health["status"] = "unhealthy"

    # Check agent initialization
    if strands_agent and strands_agent.initialization_error:
        health["dependencies"]["agent"] = {
            "status": "unhealthy",
            "error": strands_agent.initialization_error,
        }
        health["status"] = "unhealthy"

    http_status = 200 if health["status"] == "healthy" else (503 if health["status"] == "unhealthy" else 200)
    return JSONResponse(content=health, status_code=http_status)
```

---

### 14. **Async/Await Consistency**
**Status**: ⚠️ Mostly async but some blocking calls

Some I/O operations may be blocking in async context.

**What's Needed**:
- Audit all file operations: use `aiofiles`
- Audit all HTTP calls: use `aiohttp` or `httpx` with async
- Ensure all database calls are non-blocking
- Review Ollama client: wrap in executor if needed

```python
# Use async file operations
import aiofiles

async def load_config_file():
    async with aiofiles.open("config.json") as f:
        content = await f.read()
        return json.loads(content)
```

---

### 15. **PII Redaction in Logs**
**Status**: ❌ NOT IMPLEMENTED

User queries might contain sensitive information that's being logged.

**What's Needed**:
```python
# src/utils/pii_redactor.py
import re

PII_PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
    'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
    'api_key': r'[sk|pk|test_sk|test_pk]-[A-Za-z0-9]{20,}',
}

def redact_pii(text: str) -> str:
    """Redact PII from text before logging"""
    for pii_type, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", text)
    return text

# Usage in logging
logger.info(f"Query: {redact_pii(user_query)}")
```

---

## 📋 QUICK IMPLEMENTATION CHECKLIST

**Before Production Deployment**:

- [ ] **CRITICAL**
  - [ ] Configuration validation on startup
  - [ ] Request size limiting middleware
  - [ ] Security headers middleware
  - [ ] Request ID / Correlation ID tracking
  - [ ] Rate limiting on API endpoints

- [ ] **HIGH PRIORITY**
  - [ ] API key authentication
  - [ ] CORS origin whitelist (not wildcard)
  - [ ] Database migrations framework
  - [ ] Graceful shutdown with resource cleanup
  - [ ] GlobalErrorResponse implementation

- [ ] **MEDIUM PRIORITY**
  - [ ] Circuit breaker for external services
  - [ ] Structured logging with correlation IDs
  - [ ] Comprehensive health checks
  - [ ] Async/await consistency review
  - [ ] PII redaction in logs

- [ ] **DEPLOYMENT CHECKLIST**
  - [ ] All configuration variables documented in `.env.example`
  - [ ] All environment-specific configs created (dev/staging/prod)
  - [ ] Dependency versions pinned in `pyproject.toml`
  - [ ] Database initialized before startup
  - [ ] Health checks passing before accepting traffic
  - [ ] Logging configured for log aggregation service
  - [ ] Rate limiting configured appropriately
  - [ ] API documentation updated with error responses

---

## 🎯 RECOMMENDED IMPLEMENTATION ORDER

1. **Week 1**: Configuration validation, request size limits, security headers
2. **Week 2**: Request ID tracking, structured logging, graceful shutdown
3. **Week 3**: Rate limiting, authentication, CORS configuration
4. **Week 4**: Database migrations, error response standardization
5. **Week 5**: Circuit breaker, health checks, async/await audit

---

## 📚 Related Documentation

- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Global error response implementation
- [GETTING_STARTED.md](GETTING_STARTED.md) - Configuration reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [AWS_ARCHITECTURE.md](AWS_ARCHITECTURE.md) - AgentCore deployment
