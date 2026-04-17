"""Documentation Management Skill - Handles documentation analysis and generation."""

import logging

from src.tools.tool_registry import ToolDefinition, ToolRegistry

logger = logging.getLogger(__name__)


class DocumentationSkill:
    """Skill for documentation analysis, generation, and improvement.

    This skill provides tools for managing project documentation,
    analyzing existing docs, and generating new documentation.
    """

    # Skill documentation
    SKILL_DESCRIPTION = """
    # Documentation Skill

    Handles comprehensive documentation management for projects.

    ## Tools in This Skill

    - **analyze_documentation**: Analyze existing documentation for completeness and quality
    - **generate_docs**: Generate documentation from code files
    - **improve_docs**: Suggest improvements for existing documentation
    - **validate_docs_structure**: Check documentation organization and structure

    ## Use Cases
    - User wants to assess documentation quality → analyze_documentation
    - User needs API docs generated → generate_docs from source code
    - User wants to improve existing docs → improve_docs with suggestions
    - User needs to organize documentation → validate_docs_structure
    """

    @staticmethod
    def register_tools(registry: ToolRegistry, agent) -> None:
        """Register documentation tools with the agent.

        Args:
            registry: Tool registry to register with
            agent: StrandsCoreAgent instance
        """

        # Tool 1: analyze_documentation
        registry.register_tool(
            ToolDefinition(
                name="analyze_documentation",
                description="Analyze existing documentation for completeness, quality, and consistency",
                function=agent.analyze_files,  # Uses the file analysis tool from agent
                parameters={
                    "path": {
                        "type": "string",
                        "description": "Directory or file path containing documentation to analyze",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "File pattern to filter documentation files (e.g., '*.md', '*.rst')",
                        "default": "*.md",
                        "nullable": True,
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to recursively search subdirectories for documentation",
                        "default": True,
                    },
                },
                skill_category="documentation",
            )
        )

        # Tool 2: generate_docs
        registry.register_tool(
            ToolDefinition(
                name="generate_docs",
                description="Generate documentation from source code files",
                function=agent.generate_documentation,  # Uses documentation generation tool
                parameters={
                    "source_path": {
                        "type": "string",
                        "description": "Path to source file or directory to generate docs for",
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "Type of documentation to generate",
                        "enum": ["api", "readme", "guide", "reference"],
                        "default": "api",
                    },
                    "output_format": {
                        "type": "string",
                        "description": "Output format for generated documentation",
                        "enum": ["markdown", "rst", "html"],
                        "default": "markdown",
                    },
                },
                skill_category="documentation",
            )
        )

        # Tool 3: improve_docs
        registry.register_tool(
            ToolDefinition(
                name="improve_docs",
                description="Analyze documentation and provide specific improvement suggestions",
                function=agent._create_docs_improvement_tool(),
                parameters={
                    "doc_path": {
                        "type": "string",
                        "description": "Path to documentation file or directory to improve",
                    },
                    "focus_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific areas to focus improvement on",
                        "nullable": True,
                    },
                    "improvement_type": {
                        "type": "string",
                        "description": "Type of improvement to focus on",
                        "enum": ["clarity", "completeness", "structure", "examples"],
                        "default": "completeness",
                    },
                },
                skill_category="documentation",
            )
        )

        # Tool 4: validate_docs_structure
        registry.register_tool(
            ToolDefinition(
                name="validate_docs_structure",
                description="Validate documentation organization and suggest structural improvements",
                function=agent.analyze_project_structure,  # Uses structure analysis tool
                parameters={
                    "docs_path": {
                        "type": "string",
                        "description": "Path to documentation directory (e.g., 'docs/', 'documentation/')",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum directory depth to analyze",
                        "default": 3,
                    },
                    "check_standards": {
                        "type": "boolean",
                        "description": "Whether to check against documentation standards and conventions",
                        "default": True,
                    },
                },
                skill_category="documentation",
            )
        )

        logger.info("DocumentationSkill: Registered 4 documentation tools")

    @staticmethod
    def _create_docs_improvement_tool():
        """Create a specialized tool for documentation improvement suggestions."""

        from typing import Any

        def improve_documentation(
            doc_path: str,
            focus_areas: list[Any] | None = None,
            improvement_type: str = "completeness",
        ):
            """Analyze documentation and provide improvement suggestions.

            Args:
                doc_path: Path to documentation to improve
                focus_areas: Specific areas to focus on
                improvement_type: Type of improvement to prioritize

            Returns:
                Improvement suggestions and analysis
            """
            # This would be implemented with actual analysis logic
            # For now, return a representative structure
            return {
                "analyzed_path": doc_path,
                "improvement_type": improvement_type,
                "suggestions": [
                    "Add more code examples to clarify complex concepts",
                    "Improve section organization with clearer headings",
                    "Add cross-references between related sections",
                    "Include troubleshooting section for common issues",
                ],
                "quality_score": 0.75,
                "focus_areas_analyzed": focus_areas or ["structure", "completeness"],
            }

        return improve_documentation
