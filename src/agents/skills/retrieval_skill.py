"""Retrieval skill - Handles document search and context retrieval."""

import logging
from src.tools.tool_registry import ToolRegistry, ToolDefinition

logger = logging.getLogger(__name__)


class RetreivalSkill:
    """Skill for searching and retrieving documents.

    This skill provides tools for semantic search and document retrieval
    from the Milvus vector database.
    """

    # Skill documentation (would be extended with markdown in production)
    SKILL_DESCRIPTION = """
    # Retrieval Skill

    Handles semantic search and document retrieval from the knowledge base.

    ## Tools in This Skill

    - **retrieve_documents**: Search for documents similar to a query
    - **search_by_source**: Filter search results by document source
    - **list_collections**: List all available collections

    ## Use Cases
    - User asks "What is Milvus?" → retrieve_documents searches for answers
    - User wants docs from specific source → search_by_source filters results
    - User wants to see available data → list_collections shows options
    """

    @staticmethod
    def register_tools(registry: ToolRegistry, agent) -> None:
        """Register retrieval tools with the agent.

        Args:
            registry: Tool registry to register with
            agent: StrandsRAGAgent instance
        """

        # Tool 1: retrieve_documents
        registry.register_tool(
            ToolDefinition(
                name="retrieve_documents",
                description="Search for documents semantically similar to a query",
                function=agent.retrieve_documents,
                parameters={
                    "collection_name": {
                        "type": "string",
                        "description": "Name of the collection to search (e.g., 'milvus_docs', 'knowledge_base')",
                    },
                    "query": {
                        "type": "string",
                        "description": "The search query or question",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5,
                    },
                    "filter_source": {
                        "type": "string",
                        "description": "Optional source filter to narrow results",
                        "nullable": True,
                    },
                },
                skill_category="retrieval",
            )
        )

        # Tool 2: search_by_source
        registry.register_tool(
            ToolDefinition(
                name="search_by_source",
                description="Search documents filtered by a specific source",
                function=agent.search_by_source,
                parameters={
                    "collection_name": {
                        "type": "string",
                        "description": "Collection to search in",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source to filter by (e.g., 'milvus_docs')",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                },
                skill_category="retrieval",
            )
        )

        # Tool 3: list_collections
        registry.register_tool(
            ToolDefinition(
                name="list_collections",
                description="List all available collections in the vector database",
                function=agent.list_collections,
                parameters={},
                skill_category="retrieval",
            )
        )

        logger.info("Retrieval skill registered (3 tools)")
