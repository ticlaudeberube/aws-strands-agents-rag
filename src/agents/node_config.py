"""Node configuration and runtime settings for RAG graph."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NodeConfig:
    """Configuration for a single graph node."""

    name: str
    model: str
    timeout_seconds: int
    max_retries: int
    enable_metrics: bool = True
    enable_circuit_breaker: bool = True
    max_concurrent_calls: int = 10
    rate_limit_requests_per_minute: int | None = None
    description: str = ""

    def validate(self) -> bool:
        """Validate configuration values."""
        if self.timeout_seconds <= 0:
            logger.error(f"{self.name}: timeout_seconds must be > 0")
            return False
        if self.max_retries < 0:
            logger.error(f"{self.name}: max_retries must be >= 0")
            return False
        if self.max_concurrent_calls <= 0:
            logger.error(f"{self.name}: max_concurrent_calls must be > 0")
            return False
        if (
            self.rate_limit_requests_per_minute is not None
            and self.rate_limit_requests_per_minute <= 0
        ):
            logger.error(f"{self.name}: rate_limit_requests_per_minute must be > 0")
            return False
        return True

    def update(self, **kwargs: Any) -> bool:
        """Update configuration at runtime."""
        allowed_fields = {
            "model",
            "timeout_seconds",
            "max_retries",
            "enable_metrics",
            "max_concurrent_calls",
            "rate_limit_requests_per_minute",
        }

        invalid_fields = set(kwargs.keys()) - allowed_fields
        if invalid_fields:
            logger.error(f"{self.name}: Cannot update fields {invalid_fields}")
            return False

        for key, value in kwargs.items():
            setattr(self, key, value)

        if not self.validate():
            return False

        logger.info(f"{self.name}: Configuration updated: {kwargs}")
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "name": self.name,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "enable_metrics": self.enable_metrics,
            "enable_circuit_breaker": self.enable_circuit_breaker,
            "max_concurrent_calls": self.max_concurrent_calls,
            "rate_limit_requests_per_minute": self.rate_limit_requests_per_minute,
        }


class NodeConfigManager:
    """Manage configurations for all nodes in the graph."""

    def __init__(self) -> None:
        """Initialize config manager."""
        self.configs: dict[str, NodeConfig] = {}

    def register(self, config: NodeConfig) -> bool:
        """Register a node configuration."""
        if not config.validate():
            return False
        self.configs[config.name] = config
        logger.info(f"Registered config for node: {config.name}")
        return True

    def get(self, node_name: str) -> NodeConfig | None:
        """Get configuration for a node."""
        return self.configs.get(node_name)

    def update(self, node_name: str, **kwargs: Any) -> bool:
        """Update configuration for a node at runtime."""
        config = self.get(node_name)
        if not config:
            logger.error(f"Node {node_name} not found in config manager")
            return False
        return config.update(**kwargs)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Convert all configurations to dictionary."""
        return {name: config.to_dict() for name, config in self.configs.items()}

    def reset_to_defaults(self) -> None:
        """Reset all configurations to defaults."""
        self.configs.clear()
        logger.info("Configuration manager reset to defaults")


# Preset configurations for common node types
TOPIC_CHECKER_CONFIG = NodeConfig(
    name="TopicChecker",
    model="qwen2.5:0.5b",
    timeout_seconds=5,
    max_retries=2,
    enable_circuit_breaker=False,
    max_concurrent_calls=20,
    rate_limit_requests_per_minute=1000,
    description="Fast topic validation using keyword matching",
)

SECURITY_CHECKER_CONFIG = NodeConfig(
    name="SecurityChecker",
    model="qwen2.5:0.5b",
    timeout_seconds=5,
    max_retries=2,
    enable_circuit_breaker=False,
    max_concurrent_calls=20,
    rate_limit_requests_per_minute=1000,
    description="Security attack detection using pattern matching",
)

RAG_WORKER_CONFIG = NodeConfig(
    name="RAGWorker",
    model="qwen2.5:0.5b",
    timeout_seconds=30,
    max_retries=3,
    enable_circuit_breaker=True,
    max_concurrent_calls=10,
    rate_limit_requests_per_minute=100,
    description="Vector search and answer generation with RAG",
)
