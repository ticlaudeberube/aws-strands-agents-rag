"""Tool registry and management for RAG graph nodes."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Definition of a tool available to graph nodes."""

    name: str
    description: str
    func: Callable[..., Any]
    skill_name: str = "core"
    version: str = "1.0"
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the tool function."""
        if not self.enabled:
            raise ValueError(f"Tool {self.name} is disabled")
        return self.func(*args, **kwargs)

    def disable(self) -> None:
        """Disable the tool."""
        self.enabled = False
        logger.info(f"[TOOL_REGISTRY] Tool disabled: {self.name}")

    def enable(self) -> None:
        """Enable the tool."""
        self.enabled = True
        logger.info(f"[TOOL_REGISTRY] Tool enabled: {self.name}")

    def get_metadata(self) -> Dict[str, Any]:
        """Get tool metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "skill": self.skill_name,
            "version": self.version,
            "enabled": self.enabled,
            **self.metadata,
        }


class ToolRegistry:
    """Registry for managing tools available to graph nodes."""

    def __init__(self) -> None:
        """Initialize tool registry."""
        self._tools: Dict[str, ToolDefinition] = {}
        self._node_tools: Dict[str, List[str]] = {}  # node_name -> [tool_names]

    def register_tool(
        self,
        tool: ToolDefinition,
        node_names: Optional[List[str]] = None,
    ) -> bool:
        """Register a tool globally and optionally assign to nodes.

        Args:
            tool: ToolDefinition to register
            node_names: Optional list of nodes this tool is available to

        Returns:
            True if registration successful
        """
        if tool.name in self._tools:
            logger.warning(f"[TOOL_REGISTRY] Tool already registered: {tool.name}")
            return False

        self._tools[tool.name] = tool
        logger.info(
            f"[TOOL_REGISTRY] Tool registered: {tool.name} "
            f"(skill={tool.skill_name}, version={tool.version})"
        )

        if node_names:
            for node_name in node_names:
                self.assign_tool_to_node(node_name, tool.name)

        return True

    def assign_tool_to_node(self, node_name: str, tool_name: str) -> bool:
        """Assign a tool to a node.

        Args:
            node_name: Name of the node
            tool_name: Name of the tool

        Returns:
            True if assignment successful
        """
        if tool_name not in self._tools:
            logger.error(f"[TOOL_REGISTRY] Tool not found: {tool_name}")
            return False

        if node_name not in self._node_tools:
            self._node_tools[node_name] = []

        if tool_name not in self._node_tools[node_name]:
            self._node_tools[node_name].append(tool_name)
            logger.debug(f"[TOOL_REGISTRY] Tool {tool_name} assigned to node {node_name}")

        return True

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get a tool by name.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolDefinition or None if not found
        """
        return self._tools.get(tool_name)

    def get_tools_for_node(self, node_name: str) -> List[ToolDefinition]:
        """Get all tools available to a node.

        Args:
            node_name: Name of the node

        Returns:
            List of ToolDefinitions available to the node
        """
        tool_names = self._node_tools.get(node_name, [])
        tools = [self._tools[name] for name in tool_names if name in self._tools]
        return [t for t in tools if t.enabled]

    def list_tools(self, skill_name: Optional[str] = None) -> List[ToolDefinition]:
        """List all registered tools, optionally filtered by skill.

        Args:
            skill_name: Optional skill name to filter by

        Returns:
            List of ToolDefinitions
        """
        tools = list(self._tools.values())
        if skill_name:
            tools = [t for t in tools if t.skill_name == skill_name]
        return sorted(tools, key=lambda t: t.name)

    def list_skills(self) -> Dict[str, int]:
        """Get count of tools per skill.

        Returns:
            Dictionary of skill_name -> tool_count
        """
        skills: Dict[str, int] = {}
        for tool in self._tools.values():
            skills[tool.skill_name] = skills.get(tool.skill_name, 0) + 1
        return skills

    def disable_tool(self, tool_name: str) -> bool:
        """Disable a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool disabled successfully
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False
        tool.disable()
        return True

    def enable_tool(self, tool_name: str) -> bool:
        """Enable a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool enabled successfully
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False
        tool.enable()
        return True

    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool from the registry.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool removed successfully
        """
        if tool_name not in self._tools:
            return False

        del self._tools[tool_name]

        # Remove from all nodes
        for node_tools in self._node_tools.values():
            if tool_name in node_tools:
                node_tools.remove(tool_name)

        logger.info(f"[TOOL_REGISTRY] Tool removed: {tool_name}")
        return True

    def get_registry_info(self) -> Dict[str, Any]:
        """Get comprehensive registry information.

        Returns:
            Dictionary with registry statistics and tool information
        """
        return {
            "total_tools": len(self._tools),
            "skills": self.list_skills(),
            "tools": {tool_name: tool.get_metadata() for tool_name, tool in self._tools.items()},
            "nodes": {
                node: [self._tools[name].get_metadata() for name in tools if name in self._tools]
                for node, tools in self._node_tools.items()
            },
        }

    def reset(self) -> None:
        """Reset registry to empty state."""
        self._tools.clear()
        self._node_tools.clear()
        logger.info("[TOOL_REGISTRY] Registry reset")
