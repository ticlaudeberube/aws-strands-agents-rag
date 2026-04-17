## Quick Reference: Global Error Handling

### Import Error Utilities
```python
from src.api.error_responses import (
    ErrorCode,
    create_validation_error,
    create_security_error,
    create_service_error,
    create_system_error,
)
from fastapi import HTTPException
```

### Validation Error Examples

```python
# Min length violation
error = create_validation_error(
    error_code=ErrorCode.VALIDATION_MIN_LENGTH,
    message="Message too short",
    suggestion="Please type at least 2 characters",
    field="input",
    constraint="min_length",
    constraint_value="minimum 2 characters",
    value_received=text[:50],  # Truncate for security
)
raise HTTPException(status_code=400, detail=error.model_dump())
```

```python
# Max length violation
error = create_validation_error(
    error_code=ErrorCode.VALIDATION_MAX_LENGTH,
    message="Message too long",
    constraint="max_length",
    constraint_value="maximum 5000 characters",
)
raise HTTPException(status_code=400, detail=error.model_dump())
```

```python
# Suspicious pattern
error = create_validation_error(
    error_code=ErrorCode.VALIDATION_SUSPICIOUS_PATTERN,
    message="Invalid input detected",
    suggestion="Please remove suspicious characters and try again",
)
raise HTTPException(status_code=400, detail=error.model_dump())
```

### Security Error Examples

```python
# Script injection detected
error = create_security_error(
    error_code=ErrorCode.SECURITY_SCRIPT_INJECTION,
    message="Script injection detected in input",
)
raise HTTPException(status_code=400, detail=error.model_dump())
```

```python
# JavaScript protocol attack
error = create_security_error(
    error_code=ErrorCode.SECURITY_JAVASCRIPT_PROTOCOL,
    message="JavaScript protocol detected",
)
raise HTTPException(status_code=400, detail=error.model_dump())
```

```python
# Event handler injection
error = create_security_error(
    error_code=ErrorCode.SECURITY_EVENT_HANDLER,
    message="Event handler injection detected",
)
raise HTTPException(status_code=400, detail=error.model_dump())
```

### Service Error Examples

```python
# Milvus unavailable
error = create_service_error(
    error_code=ErrorCode.SERVICE_MILVUS_UNAVAILABLE,
    message="Milvus database connection failed",
    suggestion="Please check if Milvus is running. Try: docker-compose up -d",
)
raise HTTPException(status_code=503, detail=error.model_dump())
```

```python
# Ollama unavailable
error = create_service_error(
    error_code=ErrorCode.SERVICE_OLLAMA_UNAVAILABLE,
    message="Ollama LLM service is not running",
    suggestion="Please start Ollama: ollama serve",
)
raise HTTPException(status_code=503, detail=error.model_dump())
```

```python
# Agent failed to initialize
error = create_service_error(
    error_code=ErrorCode.SERVICE_AGENT_NOT_INITIALIZED,
    message="RAG agent failed to initialize",
)
raise HTTPException(status_code=503, detail=error.model_dump())
```

### System Error Examples

```python
# Unexpected internal error
error = create_system_error(
    message="An unexpected error occurred while processing your request",
    suggestion="Please try again later or contact support",
)
raise HTTPException(status_code=500, detail=error.model_dump())
```

```python
# Default system error
error = create_system_error()  # Uses defaults
raise HTTPException(status_code=500, detail=error.model_dump())
```

### Frontend Error Handling (TypeScript)

```typescript
// Display error from response
const handleError = async (response: Response) => {
  if (response.status === 400 || response.status === 500) {
    const error = await response.json();
    
    // Show message to user
    showError(error.message);
    
    // Show suggestion if available
    if (error.suggestion) {
      showHelper(error.suggestion);
    }
  }
};
```

```typescript
// Route by category
const handleError = async (response: Response) => {
  const error = await response.json();
  
  switch (error.category) {
    case 'validation_error':
      // Highlight input field, show validation feedback
      updateInputFeedback(error.message);
      break;
      
    case 'security_error':
      // Show security warning
      showSecurityAlert(error.message);
      break;
      
    case 'service_error':
      // Show maintenance message
      showMaintenanceAlert(error.message, error.suggestion);
      break;
      
    case 'system_error':
      // Show generic error
      showError('Something went wrong. Please try again.');
      break;
  }
};
```

```typescript
// Route by specific error code
const handleError = async (response: Response) => {
  const error = await response.json();
  
  // Get specific suggestion based on error type
  const suggestions: Record<string, string> = {
    'VALIDATION_MIN_LENGTH': 'Try typing a longer message',
    'VALIDATION_MAX_LENGTH': 'Your message is too long. Try a shorter question.',
    'SECURITY_SCRIPT_INJECTION': 'Suspicious content detected. Please try a different message.',
    'SERVICE_MILVUS_UNAVAILABLE': 'Database is down. Please check system status.',
    'SERVICE_OLLAMA_UNAVAILABLE': 'LLM service is down. Please check system status.',
  };
  
  const suggestion = suggestions[error.error_code];
  if (suggestion) {
    showSuggestion(suggestion);
  }
};
```

### Error Codes Cheat Sheet

**Validation** (5 codes):
- `VALIDATION_EMPTY`
- `VALIDATION_MIN_LENGTH`
- `VALIDATION_MAX_LENGTH`
- `VALIDATION_SUSPICIOUS_PATTERN`
- `VALIDATION_EXCESSIVE_REPETITION`

**Security** (7 codes):
- `SECURITY_SCRIPT_INJECTION`
- `SECURITY_JAVASCRIPT_PROTOCOL`
- `SECURITY_EVENT_HANDLER`
- `SECURITY_IFRAME_INJECTION`
- `SECURITY_OBJECT_INJECTION`
- `SECURITY_EMBED_INJECTION`
- `SECURITY_MALICIOUS_INTENT`

**Service** (5 codes):
- `SERVICE_UNAVAILABLE`
- `SERVICE_AGENT_NOT_INITIALIZED`
- `SERVICE_MCP_NOT_INITIALIZED`
- `SERVICE_MILVUS_UNAVAILABLE`
- `SERVICE_OLLAMA_UNAVAILABLE`

**System** (1 code):
- `SYSTEM_INTERNAL_ERROR`

### Testing Errors

```python
# Unit test
from src.api.error_responses import create_validation_error, ErrorCode

def test_min_length_error():
    error = create_validation_error(
        error_code=ErrorCode.VALIDATION_MIN_LENGTH,
        message="Too short",
        field="input",
        constraint="min_length",
    )
    assert error.error_code == "VALIDATION_MIN_LENGTH"
    assert error.category == "validation_error"
```

```bash
# Run error response tests
pytest tests/unit/test_api/test_error_responses.py -v

# Run API validation tests
pytest tests/integration/test_validation_api.py -v

# Run E2E tests
npx playwright test e2e/input-validation.spec.ts
```

### Complete Example Endpoint

```python
from fastapi import HTTPException
from src.api.error_responses import ErrorCode, create_validation_error
from src.config.settings import get_settings

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    settings = get_settings()
    
    # Extract user message
    user_message = extract_text_from_content(request.messages[-1].content)
    
    # Sanitize
    sanitized = sanitize_user_input(user_message, settings)
    
    # Validate
    is_valid, error_msg = validate_user_input(sanitized, settings)
    
    if not is_valid:
        # Create and raise validation error
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
    response = await agent.invoke(sanitized)
    return response
```

### Environment Configuration

```bash
# .env
MIN_MESSAGE_LENGTH=2                   # Backend minimum
MAX_MESSAGE_LENGTH=5000               # Backend maximum
ENABLE_HTML_SANITIZATION=true        # Bleach sanitization

# chatbots/react-chatbot/.env
REACT_APP_MIN_MESSAGE_LENGTH=2        # Frontend minimum
REACT_APP_MAX_MESSAGE_LENGTH=1000     # Frontend maximum
```
