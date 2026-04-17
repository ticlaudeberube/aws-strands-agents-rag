"""MCP Server for tool management and agent communication.

This module implements the Model Context Protocol server that manages tools
and enables agent communication with proper MCP compliance.
"""

import logging
import asyncio
import json
from typing import Any

from src.config import Settings
from src.agents.strands_graph_agent import StrandsGraphRAGAgent
from src.agents.skills import RetreivalSkill, AnswerGenerationSkill, KnowledgeBaseSkill
from src.tools.tool_registry import get_registry

logger = logging.getLogger(__name__)


class RAGAgentMCPServer:
    """MCP Server for RAG Agent tools and skill management."""

    def __init__(self, settings: Settings):
        """Initialize MCP Server.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.agent = StrandsGraphRAGAgent(settings)
        self.registry = get_registry()

        # Register all skills on initialization
        self._register_skills()

        logger.info(f"MCP Server initialized with {len(self.registry.list_tools())} tools")

    def _register_skills(self) -> None:
        """Register all skills with the tool registry."""
        logger.info("Registering skills...")

        RetreivalSkill.register_tools(self.registry, self.agent)
        AnswerGenerationSkill.register_tools(self.registry, self.agent)
        KnowledgeBaseSkill.register_tools(self.registry, self.agent)

        skills_info = self.registry.list_skills()
        logger.info(f"Registered {len(skills_info)} skills: {skills_info}")

    def get_tools(self) -> list:
        """Get list of available tools in MCP format.

        Returns:
            List of tool definitions
        """
        tools = []

        for tool_name, tool_def in self.registry.get_tools_dict().items():
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
            tools.append(tool_schema)

        return tools

    def get_resources(self) -> list:
        """Get list of available resources (skills) in MCP format.

        Resources represent skill categories and their documentation.

        Returns:
            List of resource definitions
        """
        resources = []

        for skill_name, tool_count in self.registry.list_skills().items():
            resource = {
                "uri": f"skill://{skill_name}",
                "name": skill_name,
                "description": f"Skill containing {tool_count} tools",
                "mimeType": "text/markdown",
            }
            resources.append(resource)

        return resources

    def get_skills(self) -> dict[str, int]:
        """Get list of available skills and their tool counts.

        Returns:
            Dictionary mapping skill names to tool counts
        """
        return self.registry.list_skills()

    def get_skill_documentation(self, skill_name: str) -> str:
        """Get documentation for a skill.

        This returns the full SKILL.md content for a skill,
        including all tool descriptions and parameters.

        Args:
            skill_name: Name of the skill

        Returns:
            Skill documentation as markdown
        """
        tools = self.registry.get_tools_by_skill(skill_name)

        if not tools:
            return f"Skill '{skill_name}' not found"

        doc = f"# {skill_name.replace('_', ' ').title()} Skill\n\n"
        doc += f"This skill contains {len(tools)} tools:\n\n"

        for tool in tools:
            doc += f"## {tool.name}\n\n"
            doc += f"**Description:** {tool.description}\n\n"

            if tool.parameters:
                doc += "**Parameters:**\n\n"
                for param_name, param_info in tool.parameters.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "")
                    param_default = param_info.get("default")

                    doc += f"- `{param_name}` ({param_type}): {param_desc}"

                    if param_default is not None:
                        doc += f" [default: {param_default}]"

                    if param_info.get("nullable"):
                        doc += " (optional)"

                    doc += "\n"

                doc += "\n"

        return doc

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool call.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result as string
        """
        try:
            tool_def = self.registry.get_tool(tool_name)

            if not tool_def:
                return f"Error: Tool '{tool_name}' not found"

            logger.info(f"Executing tool: {tool_name}")

            # Call the tool function
            result = tool_def.function(**arguments)

            logger.info(f"Tool execution succeeded: {tool_name}")
            return str(result)

        except TypeError as e:
            return f"Error: Invalid parameters for tool '{tool_name}': {str(e)}"

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}: {str(e)}", exc_info=True)
            return f"Error executing tool '{tool_name}': {str(e)}"

    def get_server_info(self) -> dict[str, Any]:
        """Get information about the server.

        Returns:
            Server metadata
        """
        return {
            "name": "RAG Agent MCP Server",
            "version": "1.0.0",
            "description": "MCP server for RAG agent with Milvus vector database and Ollama LLM",
            "tools_count": len(self.registry.list_tools()),
            "skills_count": len(self.registry.list_skills()),
            "skills": self.registry.list_skills(),
        }

    def close(self) -> None:
        """Close server and clean up resources."""
        try:
            # StrandsGraphRAGAgent doesn't have a close method, but keep for future compatibility
            if hasattr(self.agent, "close"):
                self.agent.close()
            logger.info("MCP Server closed")
        except Exception as e:
            logger.warning(f"Error during server shutdown: {e}")


# ============================================================================
# Server startup and communication interface
# ============================================================================


class MCPServerInterface:
    """Interface for MCP protocol communication."""

    def __init__(self, server: RAGAgentMCPServer):
        """Initialize the interface.

        Args:
            server: RAGAgentMCPServer instance
        """
        self.server = server

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an MCP protocol request.

        Args:
            request: MCP request dict

        Returns:
            MCP response dict
        """
        try:
            method = request.get("method")
            params = request.get("params", {})

            if method == "tools/list":
                return {
                    "status": "success",
                    "data": self.server.get_tools(),
                }

            elif method == "resources/list":
                return {
                    "status": "success",
                    "data": self.server.get_resources(),
                }

            elif method == "resources/read":
                skill_name = params.get("uri", "").replace("skill://", "")
                doc = self.server.get_skill_documentation(skill_name)
                return {
                    "status": "success",
                    "data": doc,
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = asyncio.run(self.server.call_tool(tool_name, arguments))
                return {
                    "status": "success",
                    "data": result,
                }

            elif method == "server/info":
                return {
                    "status": "success",
                    "data": self.server.get_server_info(),
                }

            else:
                return {
                    "status": "error",
                    "error": f"Unknown method: {method}",
                }

        except Exception as e:
            logger.error(f"Request handling failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }


if __name__ == "__main__":
    from src.config.settings import get_settings

    # Simple test server
    async def test_server():
        """Run a simple test of the server."""
        settings = get_settings()
        server = RAGAgentMCPServer(settings)
        interface = MCPServerInterface(server)

        print("Server initialized")
        print(f"Tools: {len(server.registry.list_tools())}")
        print(f"Skills: {server.registry.list_skills()}")

        # Test a simple request
        result = interface.handle_request(
            {
                "method": "server/info",
                "params": {},
            }
        )

        print(f"\nServer info: {json.dumps(result, indent=2)}")

        # Test tool listing
        result = interface.handle_request(
            {
                "method": "tools/list",
                "params": {},
            }
        )

        print(f"\nAvailable tools ({len(result.get('data', []))} total):")
        for tool in result.get("data", [])[:3]:
            print(f"  - {tool['name']}: {tool['description']}")

        server.close()

    asyncio.run(test_server())
