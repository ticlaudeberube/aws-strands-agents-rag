"""Knowledge base management skill - Handles document operations."""

import logging
from src.tools.tool_registry import ToolRegistry, ToolDefinition

logger = logging.getLogger(__name__)


class KnowledgeBaseSkill:
    """Skill for managing the knowledge base.

    This skill provides tools for adding, removing, and managing documents
    in the vector database.
    """

    # Skill documentation
    SKILL_DESCRIPTION = """
    # Knowledge Base Skill
    
    Manages documents and collections in the knowledge base.
    
    ## Tools in This Skill
    
    - **add_documents**: Add documents to a collection
    
    ## Use Cases
    - User provides new documents → add_documents indexes them
    - Extend the knowledge base with new content
    - Update knowledge base as new information arrives
    """

    @staticmethod
    def register_tools(registry: ToolRegistry, agent) -> None:
        """Register knowledge base management tools with the agent.

        Args:
            registry: Tool registry to register with
            agent: StrandsRAGAgent instance
        """

        # Tool 1: add_documents
        registry.register_tool(
            ToolDefinition(
                name="add_documents",
                description="Add documents to the knowledge base for indexing",
                function=agent.add_documents,
                parameters={
                    "collection_name": {
                        "type": "string",
                        "description": "Target collection to add documents to",
                    },
                    "documents": {
                        "type": "array",
                        "description": "List of documents to add. Each document should have 'text', 'source', and optional 'metadata'",
                    },
                },
                skill_category="knowledge_base",
            )
        )

        logger.info("Knowledge base skill registered (1 tool)")
