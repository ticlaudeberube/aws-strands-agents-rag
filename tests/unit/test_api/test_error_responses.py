"""Unit tests for global error response patterns."""

import pytest

from src.api.error_responses import (
    ErrorCategory,
    ErrorCode,
    GlobalErrorResponse,
    ValidationErrorDetail,
    create_security_error,
    create_service_error,
    create_system_error,
    create_validation_error,
)


class TestErrorResponseSchema:
    """Test GlobalErrorResponse Pydantic model."""

    def test_global_error_response_creation(self):
        """Test creating a GlobalErrorResponse."""
        error = GlobalErrorResponse(
            error_code="TEST_ERROR",
            category=ErrorCategory.VALIDATION_ERROR,
            message="Test error message",
        )

        assert error.error is True
        assert error.error_code == "TEST_ERROR"
        assert error.category == ErrorCategory.VALIDATION_ERROR
        assert error.message == "Test error message"
        assert error.timestamp is not None

    def test_error_response_with_details(self):
        """Test GlobalErrorResponse with validation details."""
        detail = ValidationErrorDetail(
            field="input",
            constraint="min_length",
            constraint_value="2",
            value_received="a",
        )

        error = GlobalErrorResponse(
            error_code="VALIDATION_MIN_LENGTH",
            category=ErrorCategory.VALIDATION_ERROR,
            message="Input too short",
            details=[detail],
        )

        assert error.details is not None
        assert len(error.details) == 1
        assert error.details[0].field == "input"
        assert error.details[0].constraint == "min_length"

    def test_error_response_json_serialization(self):
        """Test that GlobalErrorResponse can be serialized to JSON."""
        error = GlobalErrorResponse(
            error_code="TEST_ERROR",
            category=ErrorCategory.VALIDATION_ERROR,
            message="Test error",
        )

        json_data = error.model_dump_json()
        assert isinstance(json_data, str)
        assert "TEST_ERROR" in json_data
        assert "validation_error" in json_data  # Category is serialized as lowercase


class TestValidationErrorFactory:
    """Test create_validation_error factory function."""

    def test_create_validation_error_min_length(self):
        """Test creating a min length validation error."""
        error = create_validation_error(
            error_code=ErrorCode.VALIDATION_MIN_LENGTH,
            message="Message too short",
            suggestion="Please type at least 2 characters",
            field="input",
            constraint="min_length",
            constraint_value="minimum 2 characters",
            value_received="a",
        )

        assert error.error_code == ErrorCode.VALIDATION_MIN_LENGTH.value
        assert error.category == ErrorCategory.VALIDATION_ERROR
        assert error.message == "Message too short"
        assert error.suggestion == "Please type at least 2 characters"
        assert error.details is not None
        assert error.details[0].field == "input"

    def test_create_validation_error_max_length(self):
        """Test creating a max length validation error."""
        error = create_validation_error(
            error_code=ErrorCode.VALIDATION_MAX_LENGTH,
            message="Message too long",
            constraint="max_length",
            constraint_value="maximum 1000 characters",
        )

        assert error.error_code == ErrorCode.VALIDATION_MAX_LENGTH.value
        assert error.category == ErrorCategory.VALIDATION_ERROR

    def test_create_validation_error_value_truncation(self):
        """Test that received value is truncated for security."""
        long_value = "a" * 100
        error = create_validation_error(
            error_code=ErrorCode.VALIDATION_MIN_LENGTH,
            message="Error",
            value_received=long_value,
        )

        if error.details:
            received = error.details[0].value_received
            assert received is None or len(received) <= 50

    def test_create_validation_error_suspicious_pattern(self):
        """Test creating a suspicious pattern error."""
        error = create_validation_error(
            error_code=ErrorCode.VALIDATION_SUSPICIOUS_PATTERN,
            message="Invalid input detected",
            suggestion="Please remove suspicious characters and try again",
        )

        assert error.category == ErrorCategory.VALIDATION_ERROR
        assert error.error_code == ErrorCode.VALIDATION_SUSPICIOUS_PATTERN.value


class TestSecurityErrorFactory:
    """Test create_security_error factory function."""

    def test_create_security_error_script_injection(self):
        """Test creating a script injection security error."""
        error = create_security_error(
            error_code=ErrorCode.SECURITY_SCRIPT_INJECTION,
            message="Script injection detected in input",
        )

        assert error.error_code == ErrorCode.SECURITY_SCRIPT_INJECTION.value
        assert error.category == ErrorCategory.SECURITY_ERROR
        assert error.message == "Script injection detected in input"
        assert error.suggestion is not None

    def test_create_security_error_javascript_protocol(self):
        """Test creating a javascript: protocol error."""
        error = create_security_error(
            error_code=ErrorCode.SECURITY_JAVASCRIPT_PROTOCOL,
            message="JavaScript protocol detected",
        )

        assert error.error_code == ErrorCode.SECURITY_JAVASCRIPT_PROTOCOL.value
        assert error.category == ErrorCategory.SECURITY_ERROR

    def test_create_security_error_event_handler(self):
        """Test creating an event handler error."""
        error = create_security_error(
            error_code=ErrorCode.SECURITY_EVENT_HANDLER,
            message="Event handler injection detected",
        )

        assert error.error_code == ErrorCode.SECURITY_EVENT_HANDLER.value

    def test_security_error_has_suggestion(self):
        """Test that security errors have helpful suggestions."""
        error = create_security_error(
            error_code=ErrorCode.SECURITY_MALICIOUS_INTENT,
            message="Malicious intent detected",
        )

        assert error.suggestion is not None
        assert len(error.suggestion) > 0
        assert "security" in error.suggestion.lower()


class TestServiceErrorFactory:
    """Test create_service_error factory function."""

    def test_create_service_error_unavailable(self):
        """Test creating a service unavailable error."""
        error = create_service_error(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Service temporarily unavailable",
        )

        assert error.error_code == ErrorCode.SERVICE_UNAVAILABLE.value
        assert error.category == ErrorCategory.SERVICE_ERROR

    def test_create_service_error_milvus(self):
        """Test creating a Milvus unavailable error."""
        error = create_service_error(
            error_code=ErrorCode.SERVICE_MILVUS_UNAVAILABLE,
            message="Milvus database connection failed",
            suggestion="Please check if Milvus is running and accessible",
        )

        assert error.error_code == ErrorCode.SERVICE_MILVUS_UNAVAILABLE.value
        assert error.category == ErrorCategory.SERVICE_ERROR
        assert "Milvus" in error.message

    def test_create_service_error_ollama(self):
        """Test creating an Ollama unavailable error."""
        error = create_service_error(
            error_code=ErrorCode.SERVICE_OLLAMA_UNAVAILABLE,
            message="Ollama LLM connection failed",
        )

        assert error.error_code == ErrorCode.SERVICE_OLLAMA_UNAVAILABLE.value

    def test_service_error_has_recovery_suggestion(self):
        """Test that service errors have recovery suggestions."""
        error = create_service_error(
            error_code=ErrorCode.SERVICE_AGENT_NOT_INITIALIZED,
            message="Agent not initialized",
        )

        assert error.suggestion is not None
        assert "try again" in error.suggestion.lower()


class TestSystemErrorFactory:
    """Test create_system_error factory function."""

    def test_create_system_error_default(self):
        """Test creating a default system error."""
        error = create_system_error()

        assert error.error_code == ErrorCode.SYSTEM_INTERNAL_ERROR.value
        assert error.category == ErrorCategory.SYSTEM_ERROR
        assert error.message == "An unexpected error occurred"
        assert error.suggestion is not None

    def test_create_system_error_custom(self):
        """Test creating a custom system error."""
        error = create_system_error(
            message="Database connection failed",
            suggestion="Please restart the application",
        )

        assert error.message == "Database connection failed"
        assert error.suggestion == "Please restart the application"

    def test_system_error_code(self):
        """Test that system errors use SYSTEM_INTERNAL_ERROR code."""
        error = create_system_error(message="Custom error")
        assert error.error_code == ErrorCode.SYSTEM_INTERNAL_ERROR.value


class TestErrorCodeEnum:
    """Test ErrorCode enum values."""

    def test_validation_error_codes(self):
        """Test that validation error codes exist."""
        assert ErrorCode.VALIDATION_EMPTY.value == "VALIDATION_EMPTY"
        assert ErrorCode.VALIDATION_MIN_LENGTH.value == "VALIDATION_MIN_LENGTH"
        assert ErrorCode.VALIDATION_MAX_LENGTH.value == "VALIDATION_MAX_LENGTH"
        assert ErrorCode.VALIDATION_SUSPICIOUS_PATTERN.value == "VALIDATION_SUSPICIOUS_PATTERN"

    def test_security_error_codes(self):
        """Test that security error codes exist."""
        assert ErrorCode.SECURITY_SCRIPT_INJECTION.value == "SECURITY_SCRIPT_INJECTION"
        assert ErrorCode.SECURITY_JAVASCRIPT_PROTOCOL.value == "SECURITY_JAVASCRIPT_PROTOCOL"
        assert ErrorCode.SECURITY_EVENT_HANDLER.value == "SECURITY_EVENT_HANDLER"
        assert ErrorCode.SECURITY_MALICIOUS_INTENT.value == "SECURITY_MALICIOUS_INTENT"

    def test_service_error_codes(self):
        """Test that service error codes exist."""
        assert ErrorCode.SERVICE_UNAVAILABLE.value == "SERVICE_UNAVAILABLE"
        assert ErrorCode.SERVICE_MILVUS_UNAVAILABLE.value == "SERVICE_MILVUS_UNAVAILABLE"
        assert ErrorCode.SERVICE_OLLAMA_UNAVAILABLE.value == "SERVICE_OLLAMA_UNAVAILABLE"

    def test_system_error_code(self):
        """Test system error code."""
        assert ErrorCode.SYSTEM_INTERNAL_ERROR.value == "SYSTEM_INTERNAL_ERROR"


class TestErrorCategoryEnum:
    """Test ErrorCategory enum."""

    def test_all_categories_exist(self):
        """Test that all error categories are defined."""
        assert ErrorCategory.VALIDATION_ERROR.value == "validation_error"
        assert ErrorCategory.SECURITY_ERROR.value == "security_error"
        assert ErrorCategory.SERVICE_ERROR.value == "service_error"
        assert ErrorCategory.SYSTEM_ERROR.value == "system_error"


class TestValidationErrorDetail:
    """Test ValidationErrorDetail model."""

    def test_validation_error_detail_creation(self):
        """Test creating a ValidationErrorDetail."""
        detail = ValidationErrorDetail(
            field="username",
            constraint="min_length",
            constraint_value="3",
            value_received="ab",
        )

        assert detail.field == "username"
        assert detail.constraint == "min_length"
        assert detail.constraint_value == "3"
        assert detail.value_received == "ab"

    def test_validation_error_detail_optional_fields(self):
        """Test ValidationErrorDetail with optional fields."""
        detail = ValidationErrorDetail(
            field="input",
            constraint="max_length",
        )

        assert detail.field == "input"
        assert detail.constraint == "max_length"
        assert detail.constraint_value is None
        assert detail.value_received is None

    def test_validation_error_detail_serialization(self):
        """Test serialization of ValidationErrorDetail."""
        detail = ValidationErrorDetail(
            field="input",
            constraint="min_length",
            constraint_value="2",
        )

        json_str = detail.model_dump_json()
        assert "field" in json_str
        assert "input" in json_str
