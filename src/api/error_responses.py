"""
Global error response patterns for API validation and backend rejection handling.

Provides standardized error responses for:
- Input validation errors (too short, too long, suspicious patterns)
- Security rejection (malicious input, injection attempts)
- System errors (service unavailable, internal errors)
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ErrorCategory(str, Enum):
    """Error categories for classification and handling."""
    
    VALIDATION_ERROR = "validation_error"
    SECURITY_ERROR = "security_error"
    SERVICE_ERROR = "service_error"
    SYSTEM_ERROR = "system_error"


class ValidationErrorDetail(BaseModel):
    """Detailed validation error information."""
    
    field: str = Field(..., description="Field that failed validation")
    constraint: str = Field(..., description="Validation constraint that failed (e.g., 'min_length', 'max_length', 'suspicious_pattern')")
    value_received: Optional[str] = Field(None, description="Actual value received (truncated if too long)")
    constraint_value: Optional[str] = Field(None, description="Expected constraint value (e.g., 'minimum 2 characters')")


class GlobalErrorResponse(BaseModel):
    """Global standardized error response for all API errors."""
    
    error: bool = Field(default=True, description="Always true for error responses")
    error_code: str = Field(..., description="Machine-readable error code (e.g., 'VALIDATION_MIN_LENGTH')")
    category: ErrorCategory = Field(..., description="Error category for client-side handling")
    message: str = Field(..., description="Human-readable error message for display")
    details: Optional[list[ValidationErrorDetail]] = Field(default=None, description="Detailed error information for validation errors")
    suggestion: Optional[str] = Field(default=None, description="Suggested action to fix the error")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="ISO 8601 timestamp")
    request_id: Optional[str] = Field(default=None, description="Request ID for error tracking")


class ValidationRejection(BaseModel):
    """Backend validation rejection response (non-standard 400 error)."""
    
    rejected: bool = Field(default=True)
    reason: str = Field(..., description="Why the input was rejected")
    error_code: str = Field(..., description="Machine-readable error code")
    suggestion: Optional[str] = Field(default=None, description="How to fix it")


# ============================================================================
# Error Code Registry (Machine-readable error codes)
# ============================================================================

class ErrorCode(str, Enum):
    """Standard error codes for validation and security."""
    
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
    SECURITY_OBJECT_INJECTION = "SECURITY_OBJECT_INJECTION"
    SECURITY_EMBED_INJECTION = "SECURITY_EMBED_INJECTION"
    SECURITY_MALICIOUS_INTENT = "SECURITY_MALICIOUS_INTENT"
    
    # Service errors
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVICE_AGENT_NOT_INITIALIZED = "SERVICE_AGENT_NOT_INITIALIZED"
    SERVICE_MCP_NOT_INITIALIZED = "SERVICE_MCP_NOT_INITIALIZED"
    SERVICE_MILVUS_UNAVAILABLE = "SERVICE_MILVUS_UNAVAILABLE"
    SERVICE_OLLAMA_UNAVAILABLE = "SERVICE_OLLAMA_UNAVAILABLE"
    
    # System errors
    SYSTEM_INTERNAL_ERROR = "SYSTEM_INTERNAL_ERROR"


# ============================================================================
# Error Factory Functions (DRY pattern)
# ============================================================================

def create_validation_error(
    error_code: ErrorCode,
    message: str,
    suggestion: str = "",
    field: str = "input",
    constraint: str = "",
    constraint_value: str = "",
    value_received: str = "",
) -> GlobalErrorResponse:
    """Create a standardized validation error response.
    
    Args:
        error_code: ErrorCode enum value
        message: Human-readable error message
        suggestion: How to fix the error
        field: Field that failed validation
        constraint: Validation constraint (e.g., 'min_length')
        constraint_value: Expected value (e.g., 'minimum 2 characters')
        value_received: Actual value received (will be truncated if too long)
        
    Returns:
        GlobalErrorResponse with validation details
    """
    details = []
    if constraint and field:
        details.append(
            ValidationErrorDetail(
                field=field,
                constraint=constraint,
                constraint_value=constraint_value or "",
                value_received=value_received[:50] if value_received else None,  # Truncate for security
            )
        )
    
    return GlobalErrorResponse(
        error_code=error_code.value,
        category=ErrorCategory.VALIDATION_ERROR,
        message=message,
        details=details if details else None,
        suggestion=suggestion,
    )


def create_security_error(
    error_code: ErrorCode,
    message: str,
    suggestion: str = "This input has been rejected for security reasons. Please try again.",
) -> GlobalErrorResponse:
    """Create a standardized security error response.
    
    Args:
        error_code: ErrorCode enum value
        message: Human-readable error message
        suggestion: Recovery suggestion
        
    Returns:
        GlobalErrorResponse for security rejection
    """
    return GlobalErrorResponse(
        error_code=error_code.value,
        category=ErrorCategory.SECURITY_ERROR,
        message=message,
        suggestion=suggestion,
    )


def create_service_error(
    error_code: ErrorCode,
    message: str,
    suggestion: str = "The service is temporarily unavailable. Please try again later.",
) -> GlobalErrorResponse:
    """Create a standardized service error response.
    
    Args:
        error_code: ErrorCode enum value
        message: Human-readable error message
        suggestion: Recovery suggestion
        
    Returns:
        GlobalErrorResponse for service errors
    """
    return GlobalErrorResponse(
        error_code=error_code.value,
        category=ErrorCategory.SERVICE_ERROR,
        message=message,
        suggestion=suggestion,
    )


def create_system_error(
    message: str = "An unexpected error occurred",
    suggestion: str = "Please contact support if this issue persists.",
) -> GlobalErrorResponse:
    """Create a standardized system error response.
    
    Args:
        message: Human-readable error message
        suggestion: Recovery suggestion
        
    Returns:
        GlobalErrorResponse for system errors
    """
    return GlobalErrorResponse(
        error_code=ErrorCode.SYSTEM_INTERNAL_ERROR.value,
        category=ErrorCategory.SYSTEM_ERROR,
        message=message,
        suggestion=suggestion,
    )
