## Global Input Validation Error Handling

This document describes the unified error handling pattern for input validation across the RAG Assistant API.

> **⚠️ Implementation Status**: This design document is complete. Backend and frontend integration is in progress.
> - ✅ Client-side basic validation (ChatInput.js)
> - ✅ Server-side basic validation (api_server.py)
> - ❌ **TODO**: Structured `GlobalErrorResponse` format not yet integrated
>   - See TODOs in: `api_server.py:1310`, `App.js:406`, `ChatInput.js:72`
>   - Requires: Error code generation, category classification, detail extraction

### Overview

The system implements a **global error response pattern** that provides:
- 🎯 Machine-readable error codes for client-side handling
- 📝 Human-readable messages for user display
- 🔧 Detailed validation information for developers
- 💡 Helpful suggestions for error recovery
- 📊 Consistent error structure across all endpoints

### Error Response Structure

All validation errors follow the `GlobalErrorResponse` schema:

```json
{
  "error": true,
  "error_code": "VALIDATION_MIN_LENGTH",
  "category": "validation_error",
  "message": "Message too short (minimum 2 characters)",
  "details": [
    {
      "field": "input",
      "constraint": "min_length",
      "constraint_value": "minimum 2 characters",
      "value_received": "a"
    }
  ],
  "suggestion": "Please type at least 2 characters",
  "timestamp": "2026-04-17T14:30:45.123456",
  "request_id": null
}
```

### Error Categories

The system organizes errors into 4 categories:

#### 1. **Validation Errors** (`validation_error`)
Input doesn't meet requirements.

| Code | Description |
|------|---|
| `VALIDATION_EMPTY` | Input is empty or whitespace-only |
| `VALIDATION_MIN_LENGTH` | Input is shorter than minimum allowed |
| `VALIDATION_MAX_LENGTH` | Input is longer than maximum allowed |
| `VALIDATION_SUSPICIOUS_PATTERN` | Input contains potentially harmful patterns |
| `VALIDATION_EXCESSIVE_REPETITION` | Input has excessive character repetition (DoS protection) |

**Example Response:**
```json
{
  "error_code": "VALIDATION_MIN_LENGTH",
  "category": "validation_error",
  "message": "Message too short (minimum 2 characters)",
  "suggestion": "Please type at least 2 characters",
  "details": [
    {
      "field": "input",
      "constraint": "min_length",
      "constraint_value": "minimum 2 characters"
    }
  ]
}
```

#### 2. **Security Errors** (`security_error`)
Input contains malicious or harmful content.

| Code | Description |
|------|---|
| `SECURITY_SCRIPT_INJECTION` | Script tags detected |
| `SECURITY_JAVASCRIPT_PROTOCOL` | JavaScript: protocol detected |
| `SECURITY_EVENT_HANDLER` | Event handler injection detected |
| `SECURITY_IFRAME_INJECTION` | Iframe injection detected |
| `SECURITY_OBJECT_INJECTION` | Object injection detected |
| `SECURITY_EMBED_INJECTION` | Embed injection detected |
| `SECURITY_MALICIOUS_INTENT` | General malicious intent detected |

**Example Response:**
```json
{
  "error_code": "SECURITY_SCRIPT_INJECTION",
  "category": "security_error",
  "message": "Script injection detected in input",
  "suggestion": "This input has been rejected for security reasons. Please try again."
}
```

#### 3. **Service Errors** (`service_error`)
API services are unavailable or misconfigured.

| Code | Description |
|------|---|
| `SERVICE_UNAVAILABLE` | Service temporarily unavailable |
| `SERVICE_AGENT_NOT_INITIALIZED` | RAG agent failed to initialize |
| `SERVICE_MCP_NOT_INITIALIZED` | MCP server failed to initialize |
| `SERVICE_MILVUS_UNAVAILABLE` | Milvus database connection failed |
| `SERVICE_OLLAMA_UNAVAILABLE` | Ollama LLM service unavailable |

**Example Response:**
```json
{
  "error_code": "SERVICE_MILVUS_UNAVAILABLE",
  "category": "service_error",
  "message": "Milvus database connection failed",
  "suggestion": "Please check if Milvus is running and accessible. Try restarting the service."
}
```

#### 4. **System Errors** (`system_error`)
Unexpected internal errors.

| Code | Description |
|------|---|
| `SYSTEM_INTERNAL_ERROR` | Unexpected internal server error |

**Example Response:**
```json
{
  "error_code": "SYSTEM_INTERNAL_ERROR",
  "category": "system_error",
  "message": "An unexpected error occurred",
  "suggestion": "Please contact support if this issue persists."
}
```

### Using Error Responses in Frontend

#### 1. Display Error Message to User

```typescript
// Assuming response is a validation error
if (response.status === 400) {
  const error = await response.json();
  
  // Show human-readable message
  showErrorUI(error.message);
  
  // And optional suggestion
  if (error.suggestion) {
    showHelper(error.suggestion);
  }
}
```

#### 2. Handle Errors by Category

```typescript
const handleValidationError = (response) => {
  const error = response.data;
  
  switch (error.category) {
    case 'validation_error':
      // Show input validation feedback
      updateErrorUI(error.message);
      break;
      
    case 'security_error':
      // Show security warning
      showSecurityWarning(error.message);
      break;
      
    case 'service_error':
      // Show maintenance message
      showMaintenanceMessage(error.suggestion);
      break;
      
    case 'system_error':
      // Show generic error
      showError('Something went wrong. Please try again.');
      break;
  }
};
```

#### 3. Route Handling by Error Code

```typescript
if (response.status === 400) {
  const error = await response.json();
  
  switch (error.error_code) {
    case 'VALIDATION_MIN_LENGTH':
    case 'VALIDATION_MAX_LENGTH':
      // Highlight input field
      inputField.classList.add('error-validation');
      break;
      
    case 'SECURITY_SCRIPT_INJECTION':
    case 'SECURITY_JAVASCRIPT_PROTOCOL':
      // Show security warning with more aggressive UI
      showSecurityAlert();
      break;
      
    case 'SERVICE_MILVUS_UNAVAILABLE':
      // Offer offline mode or retry
      showRetryOption();
      break;
  }
}
```

#### 4. Extract Validation Details for Advanced UX

```typescript
const error = response.data;

if (error.details && error.details.length > 0) {
  error.details.forEach(detail => {
    console.log(`Field: ${detail.field}`);
    console.log(`Constraint: ${detail.constraint}`);
    console.log(`Expected: ${detail.constraint_value}`);
    
    // Show specific field error
    showFieldError(detail.field, detail.constraint_value);
  });
}
```

### API Validation Flow

```
User Input
    ↓
Frontend DOMPurify Sanitization
    ↓
Frontend Length Validation
    ↓
Input too short? → Show VALIDATION_MIN_LENGTH error
    ↓
XSS Pattern detected? → Show SECURITY_* error
    ↓
Send to Backend API
    ↓
Backend Bleach Sanitization
    ↓
Backend Validation (min/max length, patterns)
    ↓
Validation failed? → Return GlobalErrorResponse (400)
    ↓
Valid Input → Process with Strands Agent
    ↓
Response/Success or Service Error
```

### Backend Implementation

#### Using Error Factory Functions

```python
from src.api.error_responses import (
    ErrorCode,
    create_validation_error,
    create_security_error,
    create_service_error,
)
from fastapi import HTTPException

# Validation error
if len(text) < 2:
    error = create_validation_error(
        error_code=ErrorCode.VALIDATION_MIN_LENGTH,
        message="Message too short",
        suggestion="Please type at least 2 characters",
        field="input",
        constraint="min_length",
        constraint_value="minimum 2 characters",
        value_received=text,
    )
    raise HTTPException(status_code=400, detail=error.model_dump())

# Security error
if detect_script_injection(text):
    error = create_security_error(
        error_code=ErrorCode.SECURITY_SCRIPT_INJECTION,
        message="Script injection detected",
    )
    raise HTTPException(status_code=400, detail=error.model_dump())

# Service error
if not milvus_available():
    error = create_service_error(
        error_code=ErrorCode.SERVICE_MILVUS_UNAVAILABLE,
        message="Milvus connection failed",
        suggestion="Please check Milvus status",
    )
    raise HTTPException(status_code=503, detail=error.model_dump())
```

#### Raising Errors in Endpoints

```python
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Extract user message
    user_message = extract_text_from_content(request.messages[-1].content)
    
    # Sanitize
    sanitized = sanitize_user_input(user_message, settings)
    
    # Validate
    is_valid, error_msg = validate_user_input(sanitized, settings)
    
    if not is_valid:
        # Extract error code from error message
        error = create_validation_error(
            error_code=ErrorCode.VALIDATION_MIN_LENGTH,
            message=error_msg,
            field="input",
        )
        raise HTTPException(
            status_code=400,
            detail=error.model_dump()
        )
    
    # Process valid input
    return await agent.invoke(sanitized)
```

### Configuration

Validation limits are configurable via environment variables:

**Backend (.env):**
```bash
MIN_MESSAGE_LENGTH=2                   # Minimum message length
MAX_MESSAGE_LENGTH=5000               # Maximum message length  
ENABLE_HTML_SANITIZATION=true        # Enable bleach sanitization
```

**Frontend (react-chatbot/.env):**
```bash
REACT_APP_MIN_MESSAGE_LENGTH=2        # Frontend minimum
REACT_APP_MAX_MESSAGE_LENGTH=1000     # Frontend maximum
```

### Testing

#### Unit Tests for Error Responses

```bash
pytest tests/unit/test_api/test_error_responses.py -v
```

Tests cover:
- GlobalErrorResponse schema
- ValidationErrorDetail structure
- All error factory functions
- Error code enum values
- JSON serialization

#### Integration Tests for Validation API

```bash
pytest tests/integration/test_validation_api.py -v
```

Tests cover:
- Empty input rejection
- Min/max length validation
- XSS prevention
- Security pattern detection
- Valid input acceptance
- Error response format consistency

#### E2E Tests for Validation UI

```bash
cd chatbots/react-chatbot
npx playwright test e2e/input-validation.spec.ts --ui
```

Tests cover:
- Frontend validation feedback
- XSS prevention in frontend
- Backend rejection handling
- Error message display
- User recovery workflows
- Accessibility compliance

### Best Practices

✅ **DO:**
- Use appropriate error codes for each scenario
- Provide helpful suggestions for recovery
- Include details for validation errors
- Log errors with context for debugging
- Test error paths as thoroughly as success paths

❌ **DON'T:**
- Expose internal stack traces to users
- Include sensitive data in error messages
- Use generic "Error" messages without detail
- Forget to sanitize error output
- Mix different error response formats

### Frontend Error Handling Helpers

#### Response Interceptor for Axios

Create a reusable error parser for consistent error handling across all API calls:

```typescript
// src/utils/errorInterceptor.ts
import axios, { AxiosError } from 'axios';

export interface ParsedError {
  error_code: string;
  category: 'validation_error' | 'security_error' | 'service_error' | 'system_error';
  message: string;
  suggestion?: string;
  details?: Array<{
    field: string;
    constraint: string;
    constraint_value: string;
  }>;
  timestamp: string;
}

/**
 * Parse API error response into structured format
 * Handles both GlobalErrorResponse and legacy error formats
 */
export const parseErrorResponse = (error: AxiosError): ParsedError | null => {
  if (!error.response?.data) return null;
  
  const data = error.response.data as any;
  
  // Check if it's already a GlobalErrorResponse
  if (data.error_code && data.category) {
    return {
      error_code: data.error_code,
      category: data.category,
      message: data.message || 'An error occurred',
      suggestion: data.suggestion,
      details: data.details,
      timestamp: data.timestamp || new Date().toISOString(),
    };
  }
  
  // Fallback for legacy error format
  return {
    error_code: 'SYSTEM_INTERNAL_ERROR',
    category: 'system_error',
    message: data.detail || 'An unexpected error occurred',
    suggestion: 'Please try again or contact support',
    timestamp: new Date().toISOString(),
  };
};

/**
 * Setup Axios interceptor for automatic error handling
 */
export const setupErrorInterceptor = (axiosInstance: any) => {
  axiosInstance.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      const parsedError = parseErrorResponse(error);
      
      if (parsedError) {
        // Log structured error for debugging
        console.error('[API Error]', {
          code: parsedError.error_code,
          category: parsedError.category,
          message: parsedError.message,
          timestamp: parsedError.timestamp,
        });
      }
      
      return Promise.reject(parsedError || error);
    }
  );
};

/**
 * Usage in component:
 * 
 * try {
 *   const response = await axiosClient.post('/v1/chat/completions', data);
 * } catch (error) {
 *   const parsed = error as ParsedError;
 *   
 *   if (parsed.category === 'validation_error') {
 *     showInputError(parsed.message);
 *   } else if (parsed.category === 'security_error') {
 *     showSecurityWarning(parsed.message);
 *   } else {
 *     showGenericError(parsed.suggestion || parsed.message);
 *   }
 * }
 */
```

### Error Display Component

#### ErrorBanner Component Reference

Create a reusable error display component for consistent error presentation:

```typescript
// src/components/ErrorBanner.tsx (Recommended location)
import React from 'react';
import { ParsedError } from '../utils/errorInterceptor';
import './ErrorBanner.css';

interface ErrorBannerProps {
  error: ParsedError | null;
  onDismiss?: () => void;
  autoHideDuration?: number; // milliseconds, 0 = no auto-hide
}

/**
 * Displays structured error responses with category-specific styling
 * 
 * Features:
 * - Color-coded by error category (red for security, orange for validation, etc.)
 * - Shows both message and suggestion
 * - Lists validation details if available
 * - Auto-dismiss after configurable duration
 * - Keyboard accessible (Escape to dismiss)
 */
export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  error,
  onDismiss,
  autoHideDuration = 5000,
}) => {
  const [isVisible, setIsVisible] = React.useState(!!error);

  React.useEffect(() => {
    if (!error) {
      setIsVisible(false);
      return;
    }

    setIsVisible(true);

    if (autoHideDuration > 0) {
      const timeout = setTimeout(
        () => setIsVisible(false),
        autoHideDuration
      );
      return () => clearTimeout(timeout);
    }
  }, [error, autoHideDuration]);

  if (!error || !isVisible) return null;

  const categoryClass = {
    validation_error: 'error-validation',
    security_error: 'error-security',
    service_error: 'error-service',
    system_error: 'error-system',
  }[error.category];

  const categoryEmoji = {
    validation_error: '⚠️',
    security_error: '🔒',
    service_error: '🔧',
    system_error: '❌',
  }[error.category];

  return (
    <div
      className={`error-banner ${categoryClass}`}
      role="alert"
      aria-live="polite"
    >
      <div className="error-header">
        <span className="error-emoji">{categoryEmoji}</span>
        <span className="error-code">[{error.error_code}]</span>
      </div>

      <p className="error-message">{error.message}</p>

      {error.suggestion && (
        <p className="error-suggestion">💡 {error.suggestion}</p>
      )}

      {error.details && error.details.length > 0 && (
        <div className="error-details">
          <label>Details:</label>
          <ul>
            {error.details.map((detail, idx) => (
              <li key={idx}>
                <strong>{detail.field}:</strong> {detail.constraint_value}
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        className="error-dismiss"
        onClick={() => {
          setIsVisible(false);
          onDismiss?.();
        }}
        aria-label="Dismiss error"
      >
        ✕
      </button>
    </div>
  );
};
```

**CSS Styling** (`ErrorBanner.css`):
```css
.error-banner {
  padding: 16px;
  margin-bottom: 16px;
  border-radius: 8px;
  border-left: 4px solid;
  background-color: #fafafa;
  animation: slideDown 0.3s ease-out;
}

/* Validation errors - Orange */
.error-banner.error-validation {
  border-left-color: #f97316;
  background-color: #fef3c7;
}

/* Security errors - Red */
.error-banner.error-security {
  border-left-color: #dc2626;
  background-color: #fee2e2;
}

/* Service errors - Yellow */
.error-banner.error-service {
  border-left-color: #eab308;
  background-color: #fef3c7;
}

/* System errors - Gray */
.error-banner.error-system {
  border-left-color: #6b7280;
  background-color: #f3f4f6;
}

.error-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 600;
}

.error-emoji {
  font-size: 18px;
}

.error-code {
  font-size: 12px;
  font-family: monospace;
  opacity: 0.7;
}

.error-message {
  margin: 0 0 8px 0;
  font-size: 14px;
  line-height: 1.5;
}

.error-suggestion {
  margin: 8px 0;
  font-size: 13px;
  font-style: italic;
  opacity: 0.9;
}

.error-details {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
  font-size: 12px;
}

.error-details label {
  display: block;
  font-weight: 600;
  margin-bottom: 4px;
}

.error-details ul {
  margin: 0;
  padding-left: 16px;
}

.error-details li {
  margin: 4px 0;
}

.error-dismiss {
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  opacity: 0.6;
  padding: 4px;
}

.error-dismiss:hover {
  opacity: 1;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

### Logging Configuration

#### Backend Structured Logging

Configure Python logging to capture error context for debugging:

```python
# src/config/logging_config.py
import logging
import logging.handlers
import json
from datetime import datetime
from pathlib import Path

def setup_error_logging(log_dir: str = "logs"):
    """Configure structured logging for errors with context"""
    
    Path(log_dir).mkdir(exist_ok=True)
    
    # JSON formatter for machine-readable logs
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            
            # Add error context if it's an exception
            if record.exc_info:
                log_data["exception"] = {
                    "type": record.exc_info[0].__name__,
                    "message": str(record.exc_info[1]),
                    "traceback": self.formatException(record.exc_info),
                }
            
            # Add custom attributes (error_code, error_category, etc.)
            for key, value in record.__dict__.items():
                if key.startswith("error_"):
                    log_data[key] = value
            
            return json.dumps(log_data)
    
    # Error file handler (JSON format)
    error_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/error.log",
        maxBytes=10_000_000,  # 10MB
        backupCount=5,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    
    # Validation file handler (JSON format)
    validation_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/validation.log",
        maxBytes=5_000_000,  # 5MB
        backupCount=5,
    )
    validation_handler.setLevel(logging.WARNING)
    validation_handler.setFormatter(JSONFormatter())
    
    # Console handler (text format for development)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(validation_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger


def log_validation_error(
    logger: logging.Logger,
    error_code: str,
    message: str,
    field: str = None,
    constraint: str = None,
    user_input: str = None,
):
    """Log validation error with structured context"""
    
    # Create logger with context
    extra = {
        "error_code": error_code,
        "error_category": "validation_error",
        "field": field,
        "constraint": constraint,
        "input_length": len(user_input) if user_input else None,
    }
    
    logger.warning(
        f"Validation failed: {message}",
        extra=extra,
    )


def log_security_error(
    logger: logging.Logger,
    error_code: str,
    message: str,
    pattern_detected: str = None,
    user_input: str = None,
):
    """Log security error with structured context"""
    
    extra = {
        "error_code": error_code,
        "error_category": "security_error",
        "pattern_detected": pattern_detected,
        "input_length": len(user_input) if user_input else None,
    }
    
    logger.warning(
        f"Security violation: {message}",
        extra=extra,
    )


def log_service_error(
    logger: logging.Logger,
    error_code: str,
    message: str,
    service: str = None,
    recovery_action: str = None,
):
    """Log service error with structured context"""
    
    extra = {
        "error_code": error_code,
        "error_category": "service_error",
        "service": service,
        "recovery_action": recovery_action,
    }
    
    logger.error(
        f"Service error: {message}",
        extra=extra,
    )


# Usage in api_server.py:
# 
# from src.config.logging_config import setup_error_logging, log_validation_error
# 
# logger = setup_error_logging()
# 
# if not is_valid:
#     log_validation_error(
#         logger,
#         error_code="VALIDATION_MIN_LENGTH",
#         message="Message too short",
#         field="input",
#         constraint="min_length",
#         user_input=sanitized_message,
#     )
#     raise HTTPException(status_code=400, detail=error.model_dump())
```

#### Log Monitoring Setup

View error logs in real-time:

```bash
# Watch error logs (JSON format)
tail -f logs/error.log | jq .

# Filter by error code
tail -f logs/validation.log | jq 'select(.error_code == "VALIDATION_MIN_LENGTH")'

# View specific time range
jq 'select(.timestamp > "2026-04-17T14:00:00")' logs/error.log

# Count errors by category
jq '.error_category' logs/error.log | sort | uniq -c
```

### Future Enhancements

- [ ] Request ID injection for error tracking
- [ ] Error telemetry and analytics
- [ ] Localization of error messages
- [ ] Rate limiting with specific error codes
- [ ] Error recovery recommendations based on user history
- [ ] Structured logging with error context
