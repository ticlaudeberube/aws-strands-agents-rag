# Production Readiness Checklist

**Document Version**: 1.0
**Last Updated**: March 7, 2026
**Status**: Development → Production Migration Guide

---

## Overview

This document outlines required improvements before deploying the AWS Strands Agents RAG system to production. Issues are categorized by priority and include specific implementation guidance.

---

## 🔴 CRITICAL - Must Fix Before Production

### 1. CORS Security Configuration

**Current State**: API accepts requests from ANY domain (`allow_origins=["*"]`)

**File**: `api_server.py` (Line ~256)

**Security Risk**:
- Any website can call your API
- Enables Cross-Site Request Forgery (CSRF) attacks
- Potential data exfiltration

**Fix**:

```python
# 1. Add to .env
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# 2. Add to src/config/settings.py
class Settings(BaseSettings):
    # ... existing settings ...
    allowed_origins: str = Field(
        default="http://localhost:3000",
        env="ALLOWED_ORIGINS",
        description="Comma-separated list of allowed CORS origins"
    )

# 3. Update api_server.py CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),  # Whitelist only
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Specific methods
    allow_headers=["Content-Type", "Authorization"],  # Specific headers
    max_age=3600,  # Cache preflight for 1 hour
)
```

**Production Example**:
```bash
# Production .env
ALLOWED_ORIGINS=https://chatbot.yourcompany.com,https://www.yourcompany.com
```

---

### 2. API Key Management

**Current State**: Tavily API key stored in `.env` file (plain text)

**File**: `.env` (Line 62)

**Security Risk**:
- Keys visible to anyone with server access
- No key rotation mechanism
- Dev/prod keys not separated

**Fix Options**:

#### Option A: AWS Secrets Manager (Recommended for AWS)
```python
import boto3
from botocore.exceptions import ClientError

def get_secret(secret_name: str) -> str:
    """Retrieve secret from AWS Secrets Manager."""
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager')

    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        logger.error(f"Failed to retrieve secret: {e}")
        raise

# In settings.py
tavily_api_key: str = Field(
    default_factory=lambda: get_secret("prod/tavily-api-key")
        if os.getenv("ENV") == "production"
        else os.getenv("TAVILY_API_KEY")
)
```

#### Option B: Azure Key Vault
```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def get_azure_secret(vault_url: str, secret_name: str) -> str:
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    return client.get_secret(secret_name).value
```

#### Option C: Environment Variables with Separate Configs (Minimum)
```bash
# .env.development (DO NOT commit)
TAVILY_API_KEY=tvly-dev-xxx

# .env.production (Managed by deployment platform)
TAVILY_API_KEY=tvly-prod-yyy
```

**Best Practices**:
- Rotate keys every 90 days
- Use different keys for dev/staging/production
- Never commit `.env` files (already gitignored ✅)
- Monitor API usage for anomalies

---

## 🟡 HIGH PRIORITY - Should Fix

### 3. Console Logging in Production

**Current State**: 20+ `console.log()` statements in React components

**Files**:
- `chatbots/react-chatbot/src/App.js` (13 instances)
- `chatbots/react-chatbot/src/components/ChatMessage.js` (1 instance)
- `chatbots/react-chatbot/src/components/ChatInput.js` (1 instance)
- `chatbots/react-chatbot/src/components/CachedResponsesList.js` (6 instances)

**Issues**:
- Performance overhead in production
- Exposes internal logic to users
- Increases bundle size
- May leak sensitive data

**Fix**: Create development-only logger utility

```javascript
// src/utils/logger.js
const isDevelopment = process.env.NODE_ENV === 'development';

export const logger = {
  log: (...args) => {
    if (isDevelopment) {
      console.log(...args);
    }
  },

  warn: (...args) => {
    if (isDevelopment) {
      console.warn(...args);
    }
  },

  error: (...args) => {
    // Always log errors, but sanitize in production
    if (isDevelopment) {
      console.error(...args);
    } else {
      console.error('An error occurred. Check server logs for details.');
      // Send to error tracking service (Sentry, etc.)
    }
  },

  info: (...args) => {
    if (isDevelopment) {
      console.info(...args);
    }
  }
};

// Usage in components
import { logger } from '../utils/logger';

// Replace all console.log with:
logger.log('🌐 FORCE WEB SEARCH ACTIVE');
logger.error('API request failed:', error);
```

**Alternative**: Use webpack terser plugin to strip console.* in production

```javascript
// package.json build script
"build": "GENERATE_SOURCEMAP=false react-scripts build"

// Add to .env.production
REACT_APP_DEBUG=false
```

---

### 4. API Rate Limiting

**Current State**: No rate limiting on any endpoints

**File**: `api_server.py`

**Issues**:
- Vulnerable to DDoS attacks
- No protection against API abuse
- Uncontrolled cache warmup could overwhelm server
- Tavily API costs could spike

**Fix**: Implement FastAPI rate limiting

```bash
# Install dependency
pip install slowapi
```

```python
# api_server.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to endpoints
@app.post("/v1/chat/completions")
@limiter.limit("20/minute")  # 20 requests per minute per IP
async def chat_completions(request: ChatCompletionRequest, bypass_cache: bool = False):
    ...

@app.post("/cache/warmup")
@limiter.limit("5/hour")  # Strict limit on expensive operations
async def warmup_cache(request: WarmupRequest):
    ...

@app.get("/health")
@limiter.limit("60/minute")  # More lenient for health checks
async def health_check():
    ...
```

**Production Configuration**:
```python
# Add to settings.py
class Settings(BaseSettings):
    rate_limit_chat: str = Field(default="20/minute", env="RATE_LIMIT_CHAT")
    rate_limit_warmup: str = Field(default="5/hour", env="RATE_LIMIT_WARMUP")
    rate_limit_health: str = Field(default="60/minute", env="RATE_LIMIT_HEALTH")
```

**Considerations**:
- Use Redis for distributed rate limiting (multi-server deployments)
- Implement per-user rate limits (requires authentication)
- Add rate limit headers to responses

---

### 5. Request Validation & Size Limits

**Current State**: Missing validation for request parameters

**File**: `api_server.py`

**Issues**:
- No maximum message length → memory exhaustion
- No conversation history limit → processing delays
- `top_k` could request 1000+ results → database overload
- No `max_tokens` upper bound → excessive LLM costs

**Fix**: Add Pydantic validators

```python
from pydantic import BaseModel, Field, validator

class ChatCompletionRequest(BaseModel):
    messages: List[Dict] = Field(
        ...,
        max_items=100,
        description="Conversation history (max 100 messages)"
    )
    model: str = Field(default="rag-agent")
    temperature: Optional[float] = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM temperature (0.0-2.0)"
    )
    top_k: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of documents to retrieve (1-20)"
    )
    max_tokens: Optional[int] = Field(
        default=2048,
        ge=1,
        le=8192,
        description="Maximum tokens to generate (1-8192)"
    )
    stream: Optional[bool] = False
    force_web_search: Optional[bool] = False

    @validator('messages')
    def validate_message_content(cls, messages):
        """Validate individual message sizes."""
        MAX_MESSAGE_LENGTH = 10000  # 10k characters per message

        for idx, msg in enumerate(messages):
            # Handle both string and ContentBlock formats
            content = msg.get('content', '')

            if isinstance(content, str):
                content_text = content
            elif isinstance(content, list):
                # Strands format: [{"text": "..."}]
                content_text = " ".join(
                    block.get('text', '') for block in content if isinstance(block, dict)
                )
            else:
                raise ValueError(f"Invalid content type in message {idx}")

            if len(content_text) > MAX_MESSAGE_LENGTH:
                raise ValueError(
                    f"Message {idx} exceeds max length ({len(content_text)} > {MAX_MESSAGE_LENGTH})"
                )

        return messages

    @validator('temperature')
    def validate_temperature(cls, v):
        """Ensure temperature is reasonable."""
        if v < 0 or v > 2:
            raise ValueError("Temperature must be between 0 and 2")
        return v

class WarmupRequest(BaseModel):
    """Request model for cache warmup."""
    questions: List[str] = Field(
        ...,
        max_items=50,  # Limit batch size
        description="Questions to warmup (max 50 at once)"
    )

    @validator('questions')
    def validate_questions(cls, questions):
        for q in questions:
            if len(q) > 500:
                raise ValueError("Question too long (max 500 chars)")
        return questions
```

**Add request size limit middleware**:
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 1_048_576):  # 1MB default
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"}
                )
        return await call_next(request)

# Add to app
app.add_middleware(RequestSizeLimitMiddleware, max_size=1_048_576)  # 1MB
```

---

### 6. Error Handling & Monitoring

**Current State**: No centralized error tracking or monitoring

**Issues**:
- No visibility into production errors
- No user behavior analytics
- No performance metrics
- Difficult to debug production issues

**Fix**: Implement error tracking and monitoring

#### **Option A: Sentry (Recommended)**

```bash
# Install
pip install sentry-sdk[fastapi]
npm install @sentry/react
```

```python
# Python (api_server.py)
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    environment=settings.environment,  # dev/staging/production
    traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
    integrations=[FastApiIntegration()],
)
```

```javascript
// React (src/index.js)
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: process.env.REACT_APP_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  integrations: [
    new Sentry.BrowserTracing(),
    new Sentry.Replay(),
  ],
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,
});
```

#### **Option B: Application Insights (Azure)**

```python
from applicationinsights import TelemetryClient

tc = TelemetryClient(settings.app_insights_key)

# Track custom events
tc.track_event('chat_completion', {
    'question_length': len(question),
    'sources_count': len(sources),
    'cache_hit': is_cached
})

# Track metrics
tc.track_metric('response_time_ms', response_time)
```

#### **Add Error Boundary to React**

```javascript
// src/components/ErrorBoundary.js
import React from 'react';
import * as Sentry from "@sentry/react";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);

    // Send to Sentry
    Sentry.captureException(error, {
      contexts: { react: errorInfo }
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <h2>Something went wrong</h2>
          <p>The application encountered an error. Please refresh the page.</p>
          <button onClick={() => window.location.reload()}>
            Refresh Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default Sentry.withErrorBoundary(ErrorBoundary);
```

```javascript
// src/index.js
import ErrorBoundary from './components/ErrorBoundary';

root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
```

---

## 🟠 MEDIUM PRIORITY - Should Address

### 7. Environment-Specific Configuration

**Current State**: Same configuration files used for dev and production

**Issue**: Risk of deploying development settings to production

**Fix**: Create environment-specific config files

```bash
# React app structure
chatbots/react-chatbot/
├── .env.development      # Local dev (gitignored)
├── .env.production       # Production template (committed)
├── .env.staging          # Staging template (committed)
└── .env.example          # Documentation (committed)
```

```bash
# .env.development
REACT_APP_API_HOST=localhost
REACT_APP_API_PORT=8000
REACT_APP_API_PROTOCOL=http
REACT_APP_DEBUG=true
REACT_APP_SENTRY_DSN=

# .env.production
REACT_APP_API_HOST=api.yourcompany.com
REACT_APP_API_PORT=443
REACT_APP_API_PROTOCOL=https
REACT_APP_DEBUG=false
REACT_APP_SENTRY_DSN=https://xxx@sentry.io/yyy
```

**Python API Configuration**:

```python
# src/config/settings.py
class Settings(BaseSettings):
    environment: str = Field(default="development", env="ENV")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    class Config:
        env_file = f".env.{os.getenv('ENV', 'development')}"
```

---

### 8. Health Check Improvements

**Current State**: Health check in React runs indefinitely without timeout

**File**: `chatbots/react-chatbot/src/App.js`

**Issues**:
- No timeout on fetch requests
- Infinite retry loop on failures
- No exponential backoff

**Fix**:

```javascript
const checkApiStatus = async () => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000); // 5s timeout

  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      const data = await response.json();
      setApiStatus('connected');
      setWebSearchEnabled(data.web_search_enabled || false);
      setRetryCount(0); // Reset on success
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    clearTimeout(timeoutId);

    if (error.name === 'AbortError') {
      logger.error('Health check timeout');
    } else {
      logger.error('Health check failed:', error);
    }

    setApiStatus('disconnected');

    // Exponential backoff
    const newRetryCount = retryCount + 1;
    setRetryCount(newRetryCount);

    // Max retry delay: 30 seconds
    const backoffDelay = Math.min(1000 * Math.pow(2, newRetryCount), 30000);
    setTimeout(checkApiStatus, backoffDelay);
  }
};

// Add retry count state
const [retryCount, setRetryCount] = useState(0);
```

---

### 9. Secure Headers

**Current State**: Missing security headers

**Fix**: Add security middleware

```python
# api_server.py
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.tavily.com"
        )

        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

### 10. Logging Configuration

**Current State**: Basic logging without structured format

**Fix**: Implement structured JSON logging for production

```python
# src/config/logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add custom fields
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id

        return json.dumps(log_data)

def setup_logging(environment: str):
    """Configure logging based on environment."""
    if environment == "production":
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
    else:
        # Development: human-readable format
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
```

---

## 🔵 LOW PRIORITY - Future Improvements

### 11. Request Deduplication

**Issue**: Double-clicking send button creates duplicate API calls

**Fix**: Debounce submit or track in-flight requests

```javascript
const [isSubmitting, setIsSubmitting] = useState(false);

const handleSendMessage = async (text, forceWebSearch = false) => {
  if (isSubmitting) return; // Prevent duplicate submissions

  setIsSubmitting(true);
  try {
    // ... send message logic ...
  } finally {
    setIsSubmitting(false);
  }
};

// Disable button while submitting
<button disabled={!input.trim() || disabled || isSubmitting}>
```

---

### 12. Retry Logic for Failed Requests

**Issue**: Network failures don't retry automatically

**Fix**: Implement exponential backoff retry

```javascript
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url, options);
      if (response.ok) return response;

      // Don't retry on client errors (4xx)
      if (response.status >= 400 && response.status < 500) {
        throw new Error(`HTTP ${response.status}`);
      }
    } catch (error) {
      if (i === maxRetries - 1) throw error;

      // Exponential backoff: 1s, 2s, 4s
      const delay = 1000 * Math.pow(2, i);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

---

### 13. Caching Headers

**Issue**: No HTTP cache headers for static content

**Fix**: Add cache-control headers

```python
@app.get("/health")
async def health_check():
    return JSONResponse(
        content={...},
        headers={
            "Cache-Control": "public, max-age=30",  # Cache for 30 seconds
        }
    )

# For static assets
@app.get("/api/docs")
async def get_docs():
    return JSONResponse(
        content={...},
        headers={
            "Cache-Control": "public, max-age=3600",  # 1 hour
        }
    )
```

---

### 14. Database Connection Pooling Monitoring

**Current State**: Connection pools configured but not monitored

**Fix**: Add pool metrics

```python
from prometheus_client import Gauge

milvus_pool_size = Gauge('milvus_pool_connections', 'Milvus connection pool size')
ollama_pool_size = Gauge('ollama_pool_connections', 'Ollama connection pool size')

# Expose metrics endpoint
@app.get("/metrics")
async def metrics():
    milvus_pool_size.set(milvus_client.pool_size)
    ollama_pool_size.set(ollama_client.pool_size)
    return generate_prometheus_metrics()
```

---

## 📋 Pre-Production Deployment Checklist

Before deploying to production, ensure:

### Security
- [ ] CORS whitelist configured for production domains
- [ ] API keys moved to secrets manager (AWS/Azure)
- [ ] HTTPS enforced (redirect HTTP → HTTPS)
- [ ] Security headers middleware enabled
- [ ] Rate limiting configured and tested
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (if using SQL)
- [ ] XSS prevention (CSP headers)

### Monitoring & Logging
- [ ] Error tracking configured (Sentry/App Insights)
- [ ] Structured JSON logging enabled
- [ ] Health check endpoints verified
- [ ] Performance monitoring active
- [ ] Alerting configured for critical errors
- [ ] Log aggregation setup (CloudWatch/ELK)

### Performance
- [ ] Connection pooling optimized
- [ ] Cache hit rates monitored
- [ ] Database indexes verified
- [ ] Load testing completed
- [ ] Auto-scaling configured
- [ ] CDN setup for static assets

### Code Quality
- [ ] All `console.log` statements removed/gated
- [ ] Environment-specific configs separated
- [ ] Error boundaries added to React
- [ ] Request timeouts configured
- [ ] Retry logic implemented
- [ ] Dependencies updated to latest stable

### Operations
- [ ] Backup strategy defined
- [ ] Rollback plan documented
- [ ] Deployment pipeline automated
- [ ] Secrets rotation schedule defined
- [ ] Incident response plan created
- [ ] Documentation updated

### Testing
- [ ] Integration tests passing
- [ ] Load tests completed (>100 concurrent users)
- [ ] Security scan performed
- [ ] Accessibility audit passed
- [ ] Cross-browser testing done
- [ ] Mobile responsiveness verified

---

## Implementation Priority

**Week 1 (Critical)**:
1. Fix CORS configuration
2. Implement rate limiting
3. Add request validation
4. Move API keys to secrets manager

**Week 2 (High)**:
5. Remove console.log statements
6. Add error tracking (Sentry)
7. Implement error boundaries
8. Add security headers

**Week 3 (Medium)**:
9. Environment-specific configs
10. Structured logging
11. Health check improvements
12. Monitoring dashboards

**Week 4+ (Low)**:
13. Request deduplication
14. Retry logic
15. Additional caching
16. Performance optimizations

---

## Resources

- **FastAPI Security**: https://fastapi.tiangolo.com/tutorial/security/
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **Sentry Documentation**: https://docs.sentry.io/
- **AWS Secrets Manager**: https://docs.aws.amazon.com/secretsmanager/
- **React Error Boundaries**: https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary

---

## Contact

For questions about production deployment, contact the DevOps team or refer to the infrastructure documentation.
