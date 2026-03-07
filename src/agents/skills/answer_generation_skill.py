"""Answer generation skill - Handles LLM-based answer synthesis."""

import logging
from src.tools.tool_registry import ToolRegistry, ToolDefinition

logger = logging.getLogger(__name__)


class AnswerGenerationSkill:
    """Skill for generating answers based on context.

    This skill provides tools for synthesizing answers and generating
    text using the LLM.
    """

    # Skill documentation
    SKILL_DESCRIPTION = """
    # Answer Generation Skill

    Generates answers and synthesizes text using the local LLM.

    ## Tools in This Skill

    - **generate_answer**: Synthesis answers based on context and questions

    ## Use Cases
    - After retrieving documents, generate_answer creates a natural response
    - Summarize retrieved context into a concise answer
    - Answer the user's original question using the context
    """

    @staticmethod
    def register_tools(registry: ToolRegistry, agent) -> None:
        """Register answer generation tools with the agent.

        Args:
            registry: Tool registry to register with
            agent: StrandsRAGAgent instance
        """

        # Tool 1: generate_answer
        registry.register_tool(
            ToolDefinition(
                name="generate_answer",
                description="Generate an answer based on a question and context",
                function=agent.generate_answer,
                parameters={
                    "question": {
                        "type": "string",
                        "description": "The original user question",
                    },
                    "context": {
                        "type": "string",
                        "description": "Retrieved context or documents to use for answering",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Sampling temperature (0.0-1.0, default: 0.1 for factual)",
                        "default": 0.1,
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maximum tokens in the answer (optional)",
                        "nullable": True,
                    },
                },
                skill_category="answer_generation",
            )
        )

        logger.info("Answer generation skill registered (1 tool)")
