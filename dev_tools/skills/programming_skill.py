"""Programming Assistance Skill - Handles code analysis, review, and development tasks."""

import logging
from typing import Any
from collections.abc import Callable

from src.tools.tool_registry import ToolDefinition, ToolRegistry

logger = logging.getLogger(__name__)


class ProgrammingSkill:
    """Skill for programming assistance, code analysis, and development guidance.

    This skill provides tools for code quality assessment, architecture analysis,
    and development best practices guidance.
    """

    # Skill documentation
    SKILL_DESCRIPTION = """
    # Programming Skill

    Provides comprehensive programming assistance and code analysis capabilities.

    ## Tools in This Skill

    - **analyze_code_quality**: Assess code quality, complexity, and maintainability
    - **detect_patterns**: Identify design patterns and architectural structures
    - **assess_project_quality**: Evaluate overall project quality and provide recommendations
    - **review_code_structure**: Analyze code organization and suggest improvements
    - **validate_best_practices**: Check adherence to coding best practices

    ## Use Cases
    - User wants code quality assessment → analyze_code_quality
    - User needs architecture review → detect_patterns for design analysis
    - User wants project evaluation → assess_project_quality for overview
    - User needs refactoring guidance → review_code_structure for improvements
    - User wants standards compliance → validate_best_practices check
    """

    @staticmethod
    def register_tools(registry: ToolRegistry, agent: Any) -> None:
        """Register programming assistance tools with the agent.

        Args:
            registry: Tool registry to register with
            agent: StrandsCoreAgent instance
        """

        # Tool 1: analyze_code_quality
        registry.register_tool(
            ToolDefinition(
                name="analyze_code_quality",
                description="Analyze code quality, complexity, structure, and maintainability",
                function=agent.analyze_code_quality,  # Uses code analysis tool from agent
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "Path to code file to analyze (supports .py, .js, .ts, .java, etc.)",
                    },
                    "analysis_type": {
                        "type": "string",
                        "description": "Depth of analysis to perform",
                        "enum": ["basic", "comprehensive", "security"],
                        "default": "comprehensive",
                    },
                    "include_metrics": {
                        "type": "boolean",
                        "description": "Whether to include detailed code metrics",
                        "default": True,
                    },
                },
                skill_category="programming",
            )
        )

        # Tool 2: detect_patterns
        registry.register_tool(
            ToolDefinition(
                name="detect_patterns",
                description="Detect design patterns, architectural patterns, and code structures",
                function=agent.detect_patterns,  # Uses pattern detection tool
                parameters={
                    "directory_path": {
                        "type": "string",
                        "description": "Directory path to analyze for patterns and architecture",
                    },
                    "pattern_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific pattern types to look for (e.g., 'factory', 'singleton', 'mvc')",
                        "nullable": True,
                    },
                    "include_architecture": {
                        "type": "boolean",
                        "description": "Whether to include architectural analysis",
                        "default": True,
                    },
                },
                skill_category="programming",
            )
        )

        # Tool 3: assess_project_quality
        registry.register_tool(
            ToolDefinition(
                name="assess_project_quality",
                description="Evaluate overall project quality and provide improvement recommendations",
                function=agent.assess_quality,  # Uses quality assessment tool
                parameters={
                    "project_path": {
                        "type": "string",
                        "description": "Root path of project to assess",
                    },
                    "focus_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific areas to focus assessment on",
                        "nullable": True,
                    },
                    "include_recommendations": {
                        "type": "boolean",
                        "description": "Whether to include actionable recommendations",
                        "default": True,
                    },
                },
                skill_category="programming",
            )
        )

        # Tool 4: review_code_structure
        registry.register_tool(
            ToolDefinition(
                name="review_code_structure",
                description="Review code organization and suggest structural improvements",
                function=ProgrammingSkill._create_structure_review_tool(),
                parameters={
                    "code_path": {
                        "type": "string",
                        "description": "Path to code file or directory to review",
                    },
                    "review_focus": {
                        "type": "string",
                        "description": "Aspect of structure to focus on",
                        "enum": ["organization", "coupling", "cohesion", "complexity"],
                        "default": "organization",
                    },
                    "suggest_refactoring": {
                        "type": "boolean",
                        "description": "Whether to suggest specific refactoring opportunities",
                        "default": True,
                    },
                },
                skill_category="programming",
            )
        )

        # Tool 5: validate_best_practices
        registry.register_tool(
            ToolDefinition(
                name="validate_best_practices",
                description="Check code adherence to best practices and coding standards",
                function=ProgrammingSkill._create_best_practices_validator(),
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "Path to code file to validate against best practices",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language for language-specific checks",
                        "enum": ["python", "javascript", "typescript", "java", "auto"],
                        "default": "auto",
                    },
                    "standards": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific standards to check against (e.g., 'pep8', 'eslint')",
                        "nullable": True,
                    },
                },
                skill_category="programming",
            )
        )

        logger.info("ProgrammingSkill: Registered 5 programming assistance tools")

    @staticmethod
    def _create_structure_review_tool() -> Callable[[str, str, bool], dict[str, Any]]:
        """Create a specialized tool for code structure review."""

        def review_code_structure(
            code_path: str, review_focus: str = "organization", suggest_refactoring: bool = True
        ) -> dict[str, Any]:
            """Review code structure and organization.

            Args:
                code_path: Path to code to review
                review_focus: Aspect of structure to focus on
                suggest_refactoring: Whether to suggest refactoring

            Returns:
                Structure review with suggestions
            """

            def safe_int(val: Any, default: int = 0) -> int:
                if isinstance(val, int):
                    return val
                if isinstance(val, float):
                    return int(val)
                if isinstance(val, str):
                    try:
                        return int(val)
                    except Exception:
                        return default
                return default

            def safe_float(val: Any, default: float = 0.0) -> float:
                if isinstance(val, float):
                    return val
                if isinstance(val, int):
                    return float(val)
                if isinstance(val, str):
                    try:
                        return float(val)
                    except Exception:
                        return default
                return default

            from pathlib import Path

            path = Path(code_path)

            if not path.exists():
                return {"error": f"Path does not exist: {code_path}", "review": {}}

            review_results: dict[str, Any] = {
                "path_analyzed": str(path),
                "review_focus": review_focus,
                "structural_analysis": {},
                "issues_found": [],
                "suggestions": [],
            }

            if path.is_file():
                # Analyze single file structure
                try:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    lines = content.splitlines()

                    # Basic structural analysis
                    analysis = {
                        "total_lines": len(lines),
                        "function_count": len(
                            [line for line in lines if line.strip().startswith("def ")]
                        ),
                        "class_count": len(
                            [line for line in lines if line.strip().startswith("class ")]
                        ),
                        "import_count": len(
                            [
                                line
                                for line in lines
                                if line.strip().startswith(("import ", "from "))
                            ]
                        ),
                        "max_line_length": max(len(line) for line in lines) if lines else 0,
                    }

                    review_results["structural_analysis"] = analysis

                    # Identify issues based on focus
                    if review_focus == "organization":
                        if analysis["total_lines"] > 500:
                            review_results["issues_found"].append(
                                "File is quite large (>500 lines)"
                            )
                        if analysis["function_count"] > 20:
                            review_results["issues_found"].append("Many functions in one file")

                    elif review_focus == "complexity":
                        complexity_score = (analysis["total_lines"] / 100) + (
                            analysis["function_count"] / 5
                        )
                        if complexity_score > 8:
                            review_results["issues_found"].append(
                                f"High complexity score: {complexity_score:.1f}"
                            )

                    # Generate suggestions if requested
                    if suggest_refactoring:
                        if analysis["total_lines"] > 300:
                            review_results["suggestions"].append(
                                "Consider splitting into smaller, focused modules"
                            )
                        if analysis["class_count"] > 5:
                            review_results["suggestions"].append(
                                "Consider organizing classes into separate files"
                            )
                        if analysis["function_count"] > 15:
                            review_results["suggestions"].append(
                                "Group related functions into classes or modules"
                            )

                except Exception as e:
                    review_results["error"] = f"Could not analyze file: {e}"

            elif path.is_dir():
                # Analyze directory structure
                python_files = list(path.rglob("*.py"))

                dir_analysis = {
                    "total_files": len(python_files),
                    "avg_file_size": 0.0,  # float
                    "largest_file": "",  # str
                    "directory_depth": 0,
                }

                if python_files:
                    file_sizes: list[float] = []
                    largest_size: float = 0.0
                    largest_file: str = ""

                    for py_file in python_files:
                        try:
                            size = float(py_file.stat().st_size)
                            file_sizes.append(size)

                            if size > largest_size:
                                largest_size = size
                                largest_file = str(py_file)
                        except Exception:
                            continue

                    avg_file_size: float = (
                        float(sum(file_sizes)) / float(len(file_sizes)) if file_sizes else 0.0
                    )
                    dir_analysis["avg_file_size"] = avg_file_size
                    dir_analysis["largest_file"] = str(largest_file)

                # Calculate directory depth
                max_depth = 0
                for py_file in python_files:
                    depth = len(py_file.relative_to(path).parts) - 1
                    max_depth = max(max_depth, depth)
                dir_analysis["directory_depth"] = max_depth

                review_results["structural_analysis"] = dir_analysis

                # Directory-specific suggestions
                if suggest_refactoring:
                    directory_depth = safe_int(dir_analysis.get("directory_depth", 0))
                    if directory_depth > 4:
                        review_results["suggestions"].append(
                            "Consider flattening deep directory structure"
                        )
                    total_files = safe_int(dir_analysis.get("total_files", 0))
                    if total_files > 50:
                        review_results["suggestions"].append(
                            "Large codebase - consider organizing into packages"
                        )
                    avg_file_size_val = safe_float(dir_analysis.get("avg_file_size", 0.0))
                    if avg_file_size_val > 10000.0:  # > ~10KB average
                        review_results["suggestions"].append(
                            "Files are relatively large - consider breaking them down"
                        )

            return review_results

        return review_code_structure

    @staticmethod
    @staticmethod
    def _create_best_practices_validator() -> Callable[
        [str, str, list[str] | None], dict[str, Any]
    ]:
        """Create a tool for validating coding best practices."""

        def validate_best_practices(
            file_path: str, language: str = "auto", standards: list[str] | None = None
        ) -> dict[str, Any]:
            """Validate code against best practices and standards.

            Args:
                file_path: Path to file to validate
                language: Programming language for validation
                standards: Specific standards to check

            Returns:
                Best practices validation results
            """
            import re
            from pathlib import Path

            path = Path(file_path)

            if not path.exists():
                return {"error": f"File does not exist: {file_path}", "validation": {}}

            # Auto-detect language if needed
            if language == "auto":
                extension = path.suffix.lower()
                lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript"}
                language = lang_map.get(extension, "unknown")

            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                return {"error": f"Could not read file: {e}", "validation": {}}

            validation_results: dict[str, Any] = {
                "file": str(path),
                "language": language,
                "standards_checked": standards or ["general"],
                "passed_checks": [],
                "failed_checks": [],
                "warnings": [],
                "score": 0.0,
            }

            checks_passed: float = 0.0
            total_checks: float = 0.0

            if language == "python":
                # Python-specific best practice checks
                total_checks += 8.0

                # Check for module docstring
                if re.match(r'^\s*"""', content, re.MULTILINE):
                    validation_results["passed_checks"].append("Has module docstring")
                    checks_passed += 1
                else:
                    validation_results["failed_checks"].append("Missing module docstring")

                # Check for function docstrings
                functions_with_docs = len(re.findall(r'def\s+\w+.*?:\s*"""', content, re.DOTALL))
                total_functions = len(re.findall(r"^def\s+\w+", content, re.MULTILINE))

                if total_functions > 0:
                    doc_ratio = float(functions_with_docs) / float(total_functions)
                    if doc_ratio >= 0.8:
                        validation_results["passed_checks"].append(
                            "Good function documentation coverage"
                        )
                        checks_passed += 1
                    else:
                        validation_results["failed_checks"].append(
                            f"Low function documentation coverage: {doc_ratio:.1%}"
                        )

                # Check for type hints
                if re.search(r":\s*(str|int|float|bool|List|Dict|Optional)", content):
                    validation_results["passed_checks"].append("Uses type hints")
                    checks_passed += 1
                else:
                    validation_results["warnings"].append("Consider adding type hints")

                # Check line length (PEP 8)
                long_lines = [
                    i + 1 for i, line in enumerate(content.splitlines()) if len(line) > 100
                ]
                if not long_lines:
                    validation_results["passed_checks"].append(
                        "Follows PEP 8 line length guidelines"
                    )
                    checks_passed += 1.0
                elif len(long_lines) <= 3:
                    validation_results["warnings"].append(
                        f"Few long lines detected: lines {long_lines}"
                    )
                    checks_passed += 0.5
                else:
                    validation_results["failed_checks"].append(
                        f"Multiple long lines: {len(long_lines)} lines > 100 chars"
                    )

                # Check for proper imports
                import_section = (
                    content.split("\n\n")[0] if "\n\n" in content else content.split("\n")[0:10]
                )
                import_text = "\n".join(import_section)

                if "from" in import_text and "import" in import_text:
                    # Check import organization (basic)
                    if re.search(r"from\s+\w+.*import.*\n.*import\s+\w+", import_text):
                        validation_results["warnings"].append(
                            "Consider organizing imports (stdlib, third-party, local)"
                        )
                    else:
                        validation_results["passed_checks"].append("Reasonable import organization")
                        checks_passed += 1

                # Check for logging instead of print
                has_print = "print(" in content
                has_logging = "logging" in content or "logger" in content

                if has_logging and not has_print:
                    validation_results["passed_checks"].append(
                        "Uses logging instead of print statements"
                    )
                    checks_passed += 1.0
                elif has_print:
                    validation_results["warnings"].append(
                        "Consider using logging instead of print statements"
                    )

                # Check exception handling
                bare_except = re.search(r"except\s*:", content)
                if bare_except:
                    validation_results["failed_checks"].append("Uses bare except clause")
                else:
                    validation_results["passed_checks"].append("No bare except clauses found")
                    checks_passed += 1.0

                # Check for magic numbers
                magic_numbers = re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\b", content)
                # Filter out common acceptable numbers
                acceptable = {"0", "1", "2", "10", "100", "0.0", "1.0"}
                problematic_numbers = [n for n in magic_numbers if n not in acceptable]

                if len(problematic_numbers) <= 3:
                    validation_results["passed_checks"].append("Minimal magic numbers")
                    checks_passed += 1.0
                else:
                    validation_results["warnings"].append(
                        f"Consider using constants for magic numbers: {set(problematic_numbers[:5])}"
                    )

            else:
                # General checks for other languages
                total_checks += 3.0

                # Check for reasonable line length
                long_lines = [
                    i + 1 for i, line in enumerate(content.splitlines()) if len(line) > 120
                ]
                if len(long_lines) <= 2:
                    validation_results["passed_checks"].append("Reasonable line lengths")
                    checks_passed += 1.0
                else:
                    validation_results["failed_checks"].append(
                        f"Multiple long lines: {len(long_lines)} lines > 120 chars"
                    )

                # Check file size
                line_count = len(content.splitlines())
                if line_count <= 300:
                    validation_results["passed_checks"].append("Reasonable file size")
                    checks_passed += 1.0
                else:
                    validation_results["warnings"].append(
                        f"Large file ({line_count} lines) - consider splitting"
                    )

                # Check for comments
                comment_patterns = [r"#.*", r"//.*", r"/\*.*?\*/", r"<!--.*?-->"]
                has_comments = any(
                    re.search(pattern, content, re.DOTALL) for pattern in comment_patterns
                )

                if has_comments:
                    validation_results["passed_checks"].append("Contains comments")
                    checks_passed += 1.0
                else:
                    validation_results["warnings"].append(
                        "Consider adding comments for complex logic"
                    )

            # Calculate overall score
            if total_checks > 0:
                validation_results["score"] = round(checks_passed / total_checks, 2)

            return validation_results

        return validate_best_practices
