"""Tool registry and management for MCP integration."""

import logging
from typing import Dict, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Tool definition with metadata for MCP and skill management."""
    
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Any]
    skill_category: str = "general"
    requires_auth: bool = False
    

class ToolRegistry:
    """Registry for tools available to agents."""
    
    def __init__(self):
        """Initialize tool registry."""
        self._tools: Dict[str, ToolDefinition] = {}
        self._skills: Dict[str, list] = {}
    
    def register_tool(
        self,
        tool_def: ToolDefinition,
    ) -> None:
        """Register a tool in the registry.
        
        Args:
            tool_def: Tool definition
        """
        self._tools[tool_def.name] = tool_def
        
        # Organize by skill
        if tool_def.skill_category not in self._skills:
            self._skills[tool_def.skill_category] = []
        
        self._skills[tool_def.skill_category].append(tool_def.name)
        
        logger.info(f"Registered tool: {tool_def.name} (skill={tool_def.skill_category})")
    
    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get tool definition by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool definition or None if not found
        """
        return self._tools.get(name)
    
    def get_tools_by_skill(self, skill_category: str) -> list:
        """Get all tool definitions in a skill category.
        
        Args:
            skill_category: Skill category name
            
        Returns:
            List of tool definitions
        """
        tool_names = self._skills.get(skill_category, [])
        return [self._tools[name] for name in tool_names]
    
    def list_skills(self) -> Dict[str, int]:
        """List all skill categories and tool counts.
        
        Returns:
            Dict mapping skill name to number of tools
        """
        return {
            skill: len(tools)
            for skill, tools in self._skills.items()
        }
    
    def list_tools(self) -> Dict[str, str]:
        """List all registered tools with descriptions.
        
        Returns:
            Dict mapping tool name to description
        """
        return {
            name: tool.description
            for name, tool in self._tools.items()
        }
    
    def get_tool_names(self) -> list:
        """Get list of all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_tools_dict(self) -> Dict[str, ToolDefinition]:
        """Get all tools as dictionary.
        
        Returns:
            Dict mapping tool names to definitions
        """
        return self._tools.copy()


# Global registry instance
_global_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Get global tool registry.
    
    Returns:
        Global ToolRegistry instance
    """
    return _global_registry


def reset_registry() -> None:
    """Reset global registry (useful for testing).
    
    Warning: This clears all registered tools.
    """
    global _global_registry
    _global_registry = ToolRegistry()
    logger.warning("Global registry reset")
