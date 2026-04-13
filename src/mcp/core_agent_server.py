"""MCP Server extension for Strands Core Agent.

This module extends the existing MCP server to include the Strands Core Agent
for documentation and programming assistance, following the established patterns.
"""

import asyncio
import logging
from typing import Any, Dict, List

from src.agents.skills import DocumentationSkill, ProgrammingSkill
from src.agents.strands_core_agent import StrandsCoreAgent
from src.config import Settings
from src.tools.tool_registry import get_registry

logger = logging.getLogger(__name__)


class CoreAgentMCPServer:
    """MCP Server for Strands Core Agent tools and skills."""

    def __init__(self, settings: Settings):
        """Initialize Core Agent MCP Server.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.agent = StrandsCoreAgent(settings)
        self.registry = get_registry()

        # Register core agent skills
        self._register_core_skills()

        logger.info(
            f"Core Agent MCP Server initialized with {len(self.registry.list_tools())} total tools"
        )

    def _register_core_skills(self) -> None:
        """Register core agent skills with the tool registry."""
        logger.info("Registering core agent skills...")

        # Register documentation and programming skills
        DocumentationSkill.register_tools(self.registry, self.agent)
        ProgrammingSkill.register_tools(self.registry, self.agent)

        skills_info = self.registry.list_skills()
        logger.info(f"Total registered skills: {len(skills_info)} - {list(skills_info.keys())}")

    def get_tools(self) -> List[Dict]:
        """Get list of all available tools in MCP format.

        Returns:
            List of tool definitions including core agent tools
        """
        tools = []

        for tool_name, tool_def in self.registry.get_tools_dict().items():
            # Create MCP-compliant tool schema
            tool_schema = {
                "name": tool_name,
                "description": tool_def.description,
                "inputSchema": {
                    "type": "object",
                    "properties": tool_def.parameters,
                    "required": [
                        param_name
                        for param_name, param_info in tool_def.parameters.items()
                        if not param_info.get("nullable", False)
                        and param_info.get("default") is None
                    ],
                },
            }

            # Add skill category for organization
            if hasattr(tool_def, "skill_category"):
                tool_schema["category"] = tool_def.skill_category

            tools.append(tool_schema)

        logger.debug(f"Returning {len(tools)} tools for MCP client")
        return tools

    def get_resources(self) -> List[Dict]:
        """Get list of available resources (skills) in MCP format.

        Returns:
            List of resource definitions
        """
        resources = []

        for skill_name, tool_count in self.registry.list_skills().items():
            resource = {
                "uri": f"skill://{skill_name}",
                "name": skill_name.replace("_", " ").title(),
                "description": f"Skill containing {tool_count} tools for {skill_name.replace('_', ' ')}",
                "mimeType": "text/markdown",
            }
            resources.append(resource)

        return resources

    async def invoke_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a tool with given arguments.

        Args:
            tool_name: Name of the tool to invoke
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        try:
            # Get tool definition from registry
            tools_dict = self.registry.get_tools_dict()

            if tool_name not in tools_dict:
                return {
                    "error": f"Tool '{tool_name}' not found",
                    "available_tools": list(tools_dict.keys()),
                }

            tool_def = tools_dict[tool_name]

            # Validate required parameters
            required_params = [
                param_name
                for param_name, param_info in tool_def.parameters.items()
                if not param_info.get("nullable", False) and param_info.get("default") is None
            ]

            missing_params = [param for param in required_params if param not in arguments]
            if missing_params:
                return {
                    "error": f"Missing required parameters: {missing_params}",
                    "required_parameters": required_params,
                }

            # Invoke the tool function
            logger.info(f"Invoking tool: {tool_name} with arguments: {list(arguments.keys())}")

            if asyncio.iscoroutinefunction(tool_def.function):
                result = await tool_def.function(**arguments)
            else:
                result = tool_def.function(**arguments)

            return {
                "tool": tool_name,
                "result": result,
                "status": "success",
                "timestamp": asyncio.get_event_loop().time(),
            }

        except Exception as e:
            logger.error(f"Tool invocation failed for {tool_name}: {e}", exc_info=True)
            return {
                "error": f"Tool execution failed: {str(e)}",
                "tool": tool_name,
                "status": "error",
            }

    async def get_resource_content(self, uri: str) -> Dict[str, Any]:
        """Get content for a specific resource URI.

        Args:
            uri: Resource URI (e.g., "skill://documentation")

        Returns:
            Resource content
        """
        try:
            if not uri.startswith("skill://"):
                return {"error": f"Unsupported URI scheme: {uri}"}

            skill_name = uri.replace("skill://", "")
            skills_info = self.registry.list_skills()

            if skill_name not in skills_info:
                return {
                    "error": f"Skill '{skill_name}' not found",
                    "available_skills": list(skills_info.keys()),
                }

            # Generate skill documentation
            tools_in_skill = [
                tool_name
                for tool_name, tool_def in self.registry.get_tools_dict().items()
                if getattr(tool_def, "skill_category", None) == skill_name
            ]

            content = f"# {skill_name.replace('_', ' ').title()} Skill\n\n"
            content += f"This skill contains {len(tools_in_skill)} tools:\n\n"

            for tool_name in tools_in_skill:
                tool_def = self.registry.get_tools_dict()[tool_name]
                content += f"## {tool_name}\n"
                content += f"{tool_def.description}\n\n"

                if tool_def.parameters:
                    content += "### Parameters:\n"
                    for param_name, param_info in tool_def.parameters.items():
                        param_type = param_info.get("type", "unknown")
                        param_desc = param_info.get("description", "No description")
                        content += f"- `{param_name}` ({param_type}): {param_desc}\n"
                    content += "\n"

            return {"content": content, "mimeType": "text/markdown", "skill": skill_name}

        except Exception as e:
            logger.error(f"Resource content retrieval failed for {uri}: {e}")
            return {"error": f"Failed to retrieve resource: {str(e)}"}

    def get_skill_summary(self) -> Dict[str, Any]:
        """Get summary of all registered skills and their capabilities.

        Returns:
            Summary of skills and tools
        """
        skills_info = self.registry.list_skills()
        tools_dict = self.registry.get_tools_dict()

        summary = {"total_skills": len(skills_info), "total_tools": len(tools_dict), "skills": {}}

        for skill_name, tool_count in skills_info.items():
            skill_tools = [
                tool_name
                for tool_name, tool_def in tools_dict.items()
                if getattr(tool_def, "skill_category", None) == skill_name
            ]

            summary["skills"][skill_name] = {
                "tool_count": tool_count,
                "tools": skill_tools,
                "description": f"Skill for {skill_name.replace('_', ' ')}",
            }

        return summary


class IntegratedMCPServer:
    """Integrated MCP Server that combines RAG and Core agents."""

    def __init__(self, settings: Settings):
        """Initialize integrated MCP server.

        Args:
            settings: Application settings
        """
        self.settings = settings

        # Initialize both servers
        from src.mcp.mcp_server import RAGAgentMCPServer

        self.rag_server = RAGAgentMCPServer(settings)
        self.core_server = CoreAgentMCPServer(settings)

        logger.info("Integrated MCP Server initialized with RAG and Core agents")

    def get_all_tools(self) -> List[Dict]:
        """Get tools from both RAG and Core agents."""
        rag_tools = self.rag_server.get_tools()
        core_tools = self.core_server.get_tools()

        return rag_tools + core_tools

    def get_all_resources(self) -> List[Dict]:
        """Get resources from both servers."""
        rag_resources = self.rag_server.get_resources()
        core_resources = self.core_server.get_resources()

        return rag_resources + core_resources

    async def invoke_any_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke tool from either server."""
        # Try RAG server first
        rag_tools = {tool["name"] for tool in self.rag_server.get_tools()}

        if tool_name in rag_tools:
            # RAG server doesn't have invoke_tool method, so we'd need to add it or handle differently
            logger.info(f"Routing {tool_name} to RAG server")
            return {"error": "RAG server tool invocation not yet implemented"}
        else:
            # Try core server
            return await self.core_server.invoke_tool(tool_name, arguments)

    def get_server_status(self) -> Dict[str, Any]:
        """Get status of both servers."""
        return {
            "rag_server": {
                "skills": self.rag_server.get_skills()
                if hasattr(self.rag_server, "get_skills")
                else {},
                "tools": len(self.rag_server.get_tools()),
            },
            "core_server": {
                "skills": self.core_server.get_skill_summary()["skills"],
                "tools": len(self.core_server.get_tools()),
            },
            "total_tools": len(self.get_all_tools()),
            "total_resources": len(self.get_all_resources()),
        }
