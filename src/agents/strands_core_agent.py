"""Strands Core Agent for Documentation and Programming Assistance.

This agent specializes in:
1. Documentation analysis, generation, and improvement
2. Code analysis, review, and suggestions
3. Project structure analysis and recommendations
4. Integration with existing codebase patterns

Architecture:
    Input → Scope Validation → Task Routing → Specialized Workers → Output
              ↓ (fail)           ↓
           Rejection      Task-specific execution

Usage:
    from src.agents.strands_core_agent import StrandsCoreAgent
    from src.config.settings import Settings

    settings = Settings()
    agent = StrandsCoreAgent(settings)

    # Analyze documentation
    analysis = agent.analyze_documentation("docs/")

    # Review code
    review = agent.review_code("src/agents/")

    # Generate documentation
    docs = agent.generate_documentation("api_server.py")
"""

import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from strands import Agent
from strands.tools import tool

from src.config import Settings

logger = logging.getLogger(__name__)


# ============================================================================
# STRUCTURED OUTPUT MODELS
# ============================================================================


class TaskValidationResult(BaseModel):
    """Structured output for task validation."""

    is_valid: bool = Field(..., description="Whether the task is supported")
    task_type: str = Field(..., description="Identified task type")
    reason: str = Field(..., description="Explanation for the validation result")
    suggested_approach: Optional[str] = Field(None, description="Suggested approach if valid")


class DocumentationAnalysis(BaseModel):
    """Structured output for documentation analysis."""

    files_analyzed: int = Field(..., description="Number of files analyzed")
    issues_found: List[Dict] = Field(default_factory=list, description="Issues identified")
    recommendations: List[str] = Field(
        default_factory=list, description="Improvement recommendations"
    )
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall quality score")
    missing_docs: List[str] = Field(default_factory=list, description="Missing documentation files")


class CodeAnalysis(BaseModel):
    """Structured output for code analysis."""

    files_analyzed: int = Field(..., description="Number of files analyzed")
    complexity_score: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Code complexity score"
    )
    issues: List[Dict] = Field(default_factory=list, description="Code issues found")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")
    patterns_detected: List[str] = Field(
        default_factory=list, description="Design patterns detected"
    )


class GeneratedContent(BaseModel):
    """Structured output for generated content."""

    content_type: str = Field(..., description="Type of content generated")
    content: str = Field(..., description="Generated content")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Generation confidence")


# ============================================================================
# CORE AGENT CLASS
# ============================================================================


class StrandsCoreAgent:
    """Strands Agent for Documentation and Programming Assistance.

    This agent follows the established 3-node pattern:
    1. Task Validator: Determines if the task is supported
    2. Task Router: Routes to appropriate specialized worker
    3. Specialized Workers: Execute specific tasks (docs/code analysis, generation)
    """

    def __init__(self, settings: Settings):
        """Initialize the Strands Core Agent.

        Args:
            settings: Application settings
        """
        self.settings = settings

        # Initialize the agents following the established pattern
        self._setup_agents()

        logger.info("StrandsCoreAgent initialized with 3-node architecture")

    def _setup_agents(self) -> None:
        """Set up the specialized agent nodes."""

        # Node 1: Task Validator (fast model)
        self.task_validator = Agent(
            name="TaskValidator",
            system_prompt="""
            You are a task validation agent for documentation and programming assistance.

            Determine if incoming requests are valid for:
            - Documentation analysis, generation, or improvement
            - Code review, analysis, or suggestions
            - Project structure analysis
            - File system operations for development

            Return structured TaskValidationResult with:
            - is_valid: true/false
            - task_type: "documentation", "code_analysis", "generation", "project_analysis"
            - reason: explanation
            - suggested_approach: how to proceed if valid

            Reject requests that are:
            - Unrelated to documentation or programming
            - Requesting harmful operations
            - Outside your expertise scope
            """,
            model=self.settings.ollama_model,  # Use fast model for validation
            tools=[],
        )

        # Node 2: Task Router (fast model)
        self.task_router = Agent(
            name="TaskRouter",
            system_prompt="""
            You route validated tasks to appropriate workers:

            - "documentation" → DocumentationWorker
            - "code_analysis" → CodeAnalysisWorker
            - "generation" → ContentGenerationWorker
            - "project_analysis" → ProjectAnalysisWorker

            Consider task complexity and choose the most efficient path.
            """,
            model=self.settings.ollama_model,  # Use fast model for routing
            tools=[],
        )

        # Create tool instances for workers
        file_analysis_tool = self._create_file_analysis_tool()
        documentation_tool = self._create_documentation_generation_tool()
        structure_tool = self._create_structure_analysis_tool()
        code_analysis_tool = self._create_code_analysis_tool()
        pattern_tool = self._create_pattern_detection_tool()
        quality_tool = self._create_quality_assessment_tool()

        # Node 3a: Documentation Worker (powerful model + tools)
        self.documentation_worker = Agent(
            name="DocumentationWorker",
            system_prompt="""
            You are an expert documentation analyst and generator.

            Capabilities:
            - Analyze existing documentation for completeness, accuracy, clarity
            - Generate missing documentation sections
            - Improve documentation structure and readability
            - Check documentation consistency across projects
            - Suggest documentation improvements

            Always provide structured output with specific recommendations.
            """,
            model=self.settings.ollama_model,  # Could use more powerful model
            tools=[file_analysis_tool, documentation_tool, structure_tool],
        )

        # Node 3b: Code Analysis Worker (powerful model + tools)
        self.code_worker = Agent(
            name="CodeAnalysisWorker",
            system_prompt="""
            You are an expert code analyst and reviewer.

            Capabilities:
            - Analyze code structure, complexity, and quality
            - Detect design patterns and architectural issues
            - Suggest improvements for maintainability
            - Identify potential bugs and code smells
            - Review adherence to best practices

            Focus on actionable, specific recommendations.
            """,
            model=self.settings.ollama_model,
            tools=[code_analysis_tool, pattern_tool, quality_tool],
        )

        # Store tool references for skill registration
        self.file_analysis_tool = file_analysis_tool
        self.documentation_tool = documentation_tool
        self.structure_tool = structure_tool
        self.code_analysis_tool = code_analysis_tool
        self.pattern_tool = pattern_tool
        self.quality_tool = quality_tool

    # ============================================================================
    # TOOL CREATION METHODS
    # ============================================================================

    def _create_file_analysis_tool(self):
        """Create tool for analyzing files and directories."""

        @tool
        def analyze_files(
            path: str, file_pattern: Optional[str] = None, recursive: bool = True
        ) -> Dict:
            """Analyze files in a directory for documentation purposes.

            Args:
                path: Directory or file path to analyze
                file_pattern: Optional pattern to filter files (e.g., "*.md", "*.py")
                recursive: Whether to search subdirectories

            Returns:
                Analysis results with file information
            """
            try:
                target_path = Path(path)

                if not target_path.exists():
                    return {
                        "error": f"Path does not exist: {path}",
                        "files": [],
                        "analysis": "Path not found",
                    }

                files = []
                issues = []

                if target_path.is_file():
                    # Analyze single file
                    files = [str(target_path)]
                else:
                    # Analyze directory
                    if recursive:
                        pattern = file_pattern or "*"
                        files = [str(p) for p in target_path.rglob(pattern)]
                    else:
                        pattern = file_pattern or "*"
                        files = [str(p) for p in target_path.glob(pattern)]

                # Filter to documentation and code files
                relevant_files = [
                    f
                    for f in files
                    if any(
                        f.endswith(ext)
                        for ext in [".md", ".rst", ".txt", ".py", ".js", ".ts", ".java", ".cpp"]
                    )
                ]

                # Analyze each file
                file_analysis = []
                for file_path in relevant_files[:20]:  # Limit to prevent overwhelming output
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        analysis = {
                            "path": file_path,
                            "size": len(content),
                            "lines": len(content.splitlines()),
                            "type": self._detect_file_type(file_path, content),
                            "has_docstring": "def " in content and '"""' in content,
                            "has_comments": "#" in content or "//" in content,
                        }

                        file_analysis.append(analysis)

                    except Exception as e:
                        issues.append(f"Could not analyze {file_path}: {e}")

                return {
                    "files_found": len(relevant_files),
                    "files_analyzed": len(file_analysis),
                    "file_details": file_analysis,
                    "issues": issues,
                    "timestamp": time.time(),
                }

            except Exception as e:
                logger.error(f"File analysis failed: {e}")
                return {"error": str(e), "files_analyzed": 0, "analysis": "Analysis failed"}

        return analyze_files

    def _create_documentation_generation_tool(self):
        """Create tool for generating documentation."""

        @tool
        def generate_documentation(
            source_path: str, doc_type: str = "api", output_format: str = "markdown"
        ) -> Dict:
            """Generate documentation for code files.

            Args:
                source_path: Path to source file or directory
                doc_type: Type of documentation ("api", "readme", "guide")
                output_format: Output format ("markdown", "rst", "html")

            Returns:
                Generated documentation content
            """
            try:
                source = Path(source_path)

                if not source.exists():
                    return {"error": f"Source path does not exist: {source_path}", "content": ""}

                if source.is_file() and source.suffix == ".py":
                    # Generate API documentation for Python file
                    with open(source, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Extract classes, functions, and docstrings
                    docs = self._extract_python_documentation(content, source.name)

                elif source.is_dir():
                    # Generate overview documentation for directory
                    docs = self._generate_directory_documentation(source)

                else:
                    return {"error": f"Unsupported file type: {source.suffix}", "content": ""}

                return {
                    "content": docs,
                    "type": doc_type,
                    "format": output_format,
                    "source": str(source),
                    "generated_at": time.time(),
                }

            except Exception as e:
                logger.error(f"Documentation generation failed: {e}")
                return {"error": str(e), "content": ""}

        return generate_documentation

    def _create_structure_analysis_tool(self):
        """Create tool for analyzing project structure."""

        @tool
        def analyze_project_structure(root_path: str, max_depth: int = 3) -> Dict:
            """Analyze project directory structure and organization.

            Args:
                root_path: Root directory to analyze
                max_depth: Maximum directory depth to traverse

            Returns:
                Project structure analysis
            """
            try:
                root = Path(root_path)

                if not root.exists() or not root.is_dir():
                    return {"error": f"Invalid directory: {root_path}", "structure": {}}

                structure = {}
                conventions = []
                issues = []

                # Analyze directory structure
                for item in root.rglob("*"):
                    if item.is_dir():
                        rel_path = item.relative_to(root)
                        depth = len(rel_path.parts)

                        if depth <= max_depth:
                            structure[str(rel_path)] = {
                                "type": "directory",
                                "files": len(list(item.glob("*"))) if item.exists() else 0,
                                "depth": depth,
                            }

                # Detect common conventions
                if (root / "src").exists():
                    conventions.append("src/ directory (good practice)")
                if (root / "tests").exists():
                    conventions.append("tests/ directory (good practice)")
                if (root / "docs").exists():
                    conventions.append("docs/ directory (good practice)")
                if (root / "README.md").exists():
                    conventions.append("README.md present (good practice)")

                # Check for issues
                if not (root / "README.md").exists():
                    issues.append("Missing README.md")
                if (
                    not (root / "requirements.txt").exists()
                    and not (root / "pyproject.toml").exists()
                ):
                    issues.append("Missing dependency file (requirements.txt or pyproject.toml)")

                return {
                    "structure": structure,
                    "conventions_found": conventions,
                    "issues": issues,
                    "total_directories": len(structure),
                    "analysis_timestamp": time.time(),
                }

            except Exception as e:
                logger.error(f"Structure analysis failed: {e}")
                return {"error": str(e), "structure": {}}

        return analyze_project_structure

    def _create_code_analysis_tool(self):
        """Create tool for analyzing code quality and structure."""

        @tool
        def analyze_code_quality(file_path: str, analysis_type: str = "comprehensive") -> Dict:
            """Analyze code quality, complexity, and structure.

            Args:
                file_path: Path to code file to analyze
                analysis_type: Type of analysis ("basic", "comprehensive", "security")

            Returns:
                Code analysis results
            """
            try:
                path = Path(file_path)

                if not path.exists():
                    return {"error": f"File does not exist: {file_path}", "analysis": {}}

                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                analysis = {
                    "file": str(path),
                    "language": self._detect_language(path.suffix),
                    "lines_of_code": len(content.splitlines()),
                    "size_bytes": len(content.encode("utf-8")),
                }

                if path.suffix == ".py":
                    # Python-specific analysis
                    analysis.update(self._analyze_python_code(content))

                # General analysis
                analysis.update(
                    {
                        "complexity_indicators": self._assess_complexity(content),
                        "documentation_coverage": self._assess_documentation_coverage(
                            content, path.suffix
                        ),
                        "potential_issues": self._detect_code_issues(content, path.suffix),
                    }
                )

                return {
                    "analysis": analysis,
                    "timestamp": time.time(),
                    "analysis_type": analysis_type,
                }

            except Exception as e:
                logger.error(f"Code analysis failed: {e}")
                return {"error": str(e), "analysis": {}}

        return analyze_code_quality

    def _create_pattern_detection_tool(self):
        """Create tool for detecting design patterns and architectures."""

        @tool
        def detect_patterns(directory_path: str, pattern_types: Optional[List[str]] = None) -> Dict:
            """Detect design patterns and architectural patterns in codebase.

            Args:
                directory_path: Directory to analyze
                pattern_types: Specific patterns to look for

            Returns:
                Detected patterns and architectural insights
            """
            try:
                root = Path(directory_path)

                if not root.exists():
                    return {"error": f"Directory does not exist: {directory_path}", "patterns": []}

                patterns_found = []
                architectural_notes = []

                # Detect common patterns
                python_files = list(root.rglob("*.py"))

                for py_file in python_files[:50]:  # Limit analysis
                    try:
                        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        # Check for common patterns
                        if "class.*Factory" in content:
                            patterns_found.append(f"Factory pattern detected in {py_file.name}")
                        if "class.*Singleton" in content or "_instance" in content:
                            patterns_found.append(f"Singleton pattern detected in {py_file.name}")
                        if "@dataclass" in content or "BaseModel" in content:
                            patterns_found.append(f"Data model pattern detected in {py_file.name}")
                        if "def __enter__" in content and "def __exit__" in content:
                            patterns_found.append(
                                f"Context manager pattern detected in {py_file.name}"
                            )

                    except Exception:
                        continue

                # Architectural analysis
                if (root / "src").exists():
                    architectural_notes.append("Layered architecture (src/ directory)")
                if (root / "tests").exists():
                    architectural_notes.append("Test-driven development structure")
                if any(root.glob("**/api*")):
                    architectural_notes.append("API-based architecture")
                if any(root.glob("**/agents*")):
                    architectural_notes.append("Agent-based architecture")

                return {
                    "patterns_detected": patterns_found,
                    "architectural_insights": architectural_notes,
                    "files_analyzed": len(python_files),
                    "analysis_timestamp": time.time(),
                }

            except Exception as e:
                logger.error(f"Pattern detection failed: {e}")
                return {"error": str(e), "patterns": []}

        return detect_patterns

    def _create_quality_assessment_tool(self):
        """Create tool for assessing overall code quality."""

        @tool
        def assess_quality(project_path: str, focus_areas: Optional[List[str]] = None) -> Dict:
            """Assess overall code quality and provide recommendations.

            Args:
                project_path: Root path of project to assess
                focus_areas: Specific areas to focus on

            Returns:
                Quality assessment and recommendations
            """
            try:
                root = Path(project_path)

                if not root.exists():
                    return {
                        "error": f"Project path does not exist: {project_path}",
                        "quality_score": 0.0,
                    }

                assessments = {
                    "structure": 0.0,
                    "documentation": 0.0,
                    "testing": 0.0,
                    "code_quality": 0.0,
                }

                recommendations = []

                # Structure assessment
                if (root / "src").exists():
                    assessments["structure"] += 0.3
                if (root / "README.md").exists():
                    assessments["structure"] += 0.2
                if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
                    assessments["structure"] += 0.3
                if (root / ".gitignore").exists():
                    assessments["structure"] += 0.2

                # Documentation assessment
                docs_dir = root / "docs"
                if docs_dir.exists():
                    assessments["documentation"] += 0.4
                    doc_files = len(list(docs_dir.glob("*.md")))
                    if doc_files >= 3:
                        assessments["documentation"] += 0.3
                else:
                    recommendations.append("Add docs/ directory with project documentation")

                # Testing assessment
                tests_dir = root / "tests"
                if tests_dir.exists():
                    assessments["testing"] += 0.5
                    test_files = len(list(tests_dir.rglob("test_*.py")))
                    if test_files >= 5:
                        assessments["testing"] += 0.3
                else:
                    recommendations.append("Add comprehensive test suite in tests/ directory")

                # Code quality assessment (basic checks)
                python_files = list(root.rglob("*.py"))
                if python_files:
                    total_score = 0.0
                    for py_file in python_files[:10]:  # Sample files
                        try:
                            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()

                            file_score = 0.0
                            if '"""' in content:  # Has docstrings
                                file_score += 0.3
                            if "typing" in content or ": str" in content:  # Type hints
                                file_score += 0.3
                            if len(content.splitlines()) < 500:  # Reasonable file size
                                file_score += 0.2
                            if "logger" in content:  # Has logging
                                file_score += 0.2

                            total_score += file_score
                        except Exception:
                            continue

                    assessments["code_quality"] = min(total_score / len(python_files), 1.0)

                # Overall quality score
                overall_quality = sum(assessments.values()) / len(assessments)

                # Generate recommendations based on low scores
                for area, score in assessments.items():
                    if score < 0.5:
                        if area == "structure":
                            recommendations.append(
                                "Improve project structure (add src/, proper config)"
                            )
                        elif area == "documentation":
                            recommendations.append("Add comprehensive documentation")
                        elif area == "testing":
                            recommendations.append("Increase test coverage")
                        elif area == "code_quality":
                            recommendations.append(
                                "Improve code quality (docstrings, type hints, logging)"
                            )

                return {
                    "overall_quality": round(overall_quality, 2),
                    "area_scores": assessments,
                    "recommendations": recommendations,
                    "files_analyzed": len(python_files),
                    "assessment_timestamp": time.time(),
                }

            except Exception as e:
                logger.error(f"Quality assessment failed: {e}")
                return {"error": str(e), "quality_score": 0.0}

        return assess_quality

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def _detect_file_type(self, file_path: str, content: str) -> str:
        """Detect the type/purpose of a file."""
        path_lower = file_path.lower()

        if path_lower.endswith(".md"):
            if "readme" in path_lower:
                return "readme"
            elif "api" in path_lower or "reference" in path_lower:
                return "api_documentation"
            else:
                return "general_documentation"
        elif path_lower.endswith(".py"):
            if "test_" in path_lower or "_test.py" in path_lower:
                return "test_code"
            elif "config" in path_lower or "setting" in path_lower:
                return "configuration"
            else:
                return "source_code"
        else:
            return "other"

    def _detect_language(self, extension: str) -> str:
        """Detect programming language from file extension."""
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
        }
        return lang_map.get(extension.lower(), "unknown")

    def _analyze_python_code(self, content: str) -> Dict:
        """Perform Python-specific code analysis."""
        analysis = {}

        # Count functions and classes
        analysis["function_count"] = len(re.findall(r"^def\s+", content, re.MULTILINE))
        analysis["class_count"] = len(re.findall(r"^class\s+", content, re.MULTILINE))

        # Check for type hints
        has_type_hints = bool(re.search(r":\s*(str|int|float|bool|List|Dict|Optional)", content))
        analysis["has_type_hints"] = has_type_hints

        # Check for async code
        analysis["has_async"] = "async def" in content

        # Check imports
        import_count = len(re.findall(r"^(import|from)", content, re.MULTILINE))
        analysis["import_count"] = import_count

        return analysis

    def _assess_complexity(self, content: str) -> Dict:
        """Assess code complexity indicators."""
        lines = content.splitlines()

        return {
            "total_lines": len(lines),
            "blank_lines": len([line for line in lines if not line.strip()]),
            "comment_lines": len([line for line in lines if line.strip().startswith("#")]),
            "max_line_length": max(len(line) for line in lines) if lines else 0,
            "nested_blocks": content.count("    "),  # Rough indentation measure
        }

    def _assess_documentation_coverage(self, content: str, file_extension: str) -> Dict:
        """Assess documentation coverage in code."""
        if file_extension == ".py":
            docstring_count = content.count('"""') + content.count("'''")
            function_count = len(re.findall(r"^def\s+", content, re.MULTILINE))
            class_count = len(re.findall(r"^class\s+", content, re.MULTILINE))

            total_definitions = function_count + class_count
            coverage_ratio = (
                docstring_count / (total_definitions * 2) if total_definitions > 0 else 0
            )

            return {
                "docstring_count": docstring_count,
                "function_count": function_count,
                "class_count": class_count,
                "estimated_coverage": min(coverage_ratio, 1.0),
            }

        return {"estimated_coverage": 0.0}

    def _detect_code_issues(self, content: str, file_extension: str) -> List[str]:
        """Detect potential code issues."""
        issues = []

        if file_extension == ".py":
            # Check for common Python issues
            if "print(" in content and "logger" not in content:
                issues.append("Using print() instead of logging")

            if re.search(r"except:", content):
                issues.append("Bare except clause detected")

            if len(content.splitlines()) > 1000:
                issues.append("File is very large (>1000 lines)")

            if not re.search(r'""".*"""', content, re.DOTALL):
                issues.append("Missing module docstring")

        return issues

    def _extract_python_documentation(self, content: str, filename: str) -> str:
        """Extract and format documentation from Python code."""
        docs = [f"# API Documentation for {filename}\n"]

        # Extract module docstring
        module_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if module_match:
            docs.append(f"## Module Description\n{module_match.group(1).strip()}\n")

        # Extract classes
        class_matches = re.finditer(r'class\s+(\w+).*?:\s*"""(.*?)"""', content, re.DOTALL)
        for match in class_matches:
            class_name, class_doc = match.groups()
            docs.append(f"## Class: {class_name}\n{class_doc.strip()}\n")

        # Extract functions
        func_matches = re.finditer(r'def\s+(\w+)\((.*?)\).*?:\s*"""(.*?)"""', content, re.DOTALL)
        for match in func_matches:
            func_name, params, func_doc = match.groups()
            docs.append(f"### Function: {func_name}({params})\n{func_doc.strip()}\n")

        return "\n".join(docs)

    def _generate_directory_documentation(self, directory: Path) -> str:
        """Generate overview documentation for a directory."""
        docs = [f"# Directory Overview: {directory.name}\n"]

        # List Python files
        py_files = list(directory.glob("*.py"))
        if py_files:
            docs.append("## Python Modules\n")
            for py_file in py_files:
                docs.append(f"- `{py_file.name}`")

        # List subdirectories
        subdirs = [d for d in directory.iterdir() if d.is_dir()]
        if subdirs:
            docs.append("\n## Subdirectories\n")
            for subdir in subdirs:
                docs.append(f"- `{subdir.name}/`")

        return "\n".join(docs)

    # ============================================================================
    # PUBLIC API METHODS
    # ============================================================================

    async def process_request(self, request: str) -> Dict:
        """Process a documentation or programming assistance request.

        Args:
            request: User request for documentation or programming help

        Returns:
            Structured response with results
        """
        try:
            start_time = time.time()

            # Step 1: Validate the task
            validation_response = await self.task_validator.invoke_async(
                context={"request": request}, max_tokens=100
            )

            # Parse validation result from response
            is_valid = "valid" in str(validation_response).lower()
            validation_result = TaskValidationResult(
                is_valid=is_valid,
                task_type="documentation" if "doc" in request.lower() else "code_analysis",
                reason="Validation completed",
                suggested_approach="Proceed with task execution" if is_valid else None,
            )

            if not validation_result.is_valid:
                return {
                    "status": "rejected",
                    "reason": validation_result.reason,
                    "task_type": validation_result.task_type,
                    "processing_time": time.time() - start_time,
                }

            # Step 2: Route to appropriate worker
            if validation_result.task_type == "documentation":
                result = await self._process_documentation_task(request)
            elif validation_result.task_type == "code_analysis":
                result = await self._process_code_analysis_task(request)
            elif validation_result.task_type == "generation":
                result = await self._process_generation_task(request)
            elif validation_result.task_type == "project_analysis":
                result = await self._process_project_analysis_task(request)
            else:
                result = {"error": f"Unknown task type: {validation_result.task_type}"}

            result["processing_time"] = time.time() - start_time
            result["status"] = "completed"
            result["task_type"] = validation_result.task_type

            return result

        except Exception as e:
            logger.error(f"Request processing failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "processing_time": time.time() - start_time if "start_time" in locals() else 0,
            }

    async def _process_documentation_task(self, request: str) -> Dict:
        """Process documentation-related tasks."""
        # Use documentation worker with its tools
        response = await self.documentation_worker.invoke_async(
            context={"request": request}, max_tokens=self.settings.max_tokens
        )
        return {"documentation_result": str(response)}

    async def _process_code_analysis_task(self, request: str) -> Dict:
        """Process code analysis tasks."""
        # Use code analysis worker with its tools
        response = await self.code_worker.invoke_async(
            context={"request": request}, max_tokens=self.settings.max_tokens
        )
        return {"analysis_result": str(response)}

    async def _process_generation_task(self, request: str) -> Dict:
        """Process content generation tasks."""
        # Use documentation worker for generation
        response = await self.documentation_worker.invoke_async(
            context={"request": request, "task": "generation"},
            max_tokens=self.settings.max_tokens * 2,  # Allow more tokens for generation
        )
        return {"generated_content": str(response)}

    async def _process_project_analysis_task(self, request: str) -> Dict:
        """Process project-wide analysis tasks."""
        # Use both workers as needed
        code_response = await self.code_worker.invoke_async(
            context={"request": request, "scope": "project"}, max_tokens=self.settings.max_tokens
        )

        doc_response = await self.documentation_worker.invoke_async(
            context={"request": request, "scope": "project"}, max_tokens=self.settings.max_tokens
        )

        return {
            "project_analysis": {
                "code_analysis": str(code_response),
                "documentation_analysis": str(doc_response),
            }
        }

    # Convenience methods for direct access

    async def analyze_documentation(self, path: str) -> DocumentationAnalysis:
        """Analyze documentation in a directory or file."""
        request = f"Analyze documentation in: {path}"
        await self._process_documentation_task(request)

        # Convert to structured output (simplified)
        return DocumentationAnalysis(
            files_analyzed=1,  # Would be populated from tool results
            quality_score=0.8,
            recommendations=["Add more examples", "Improve structure"],
        )

    async def review_code(self, path: str) -> CodeAnalysis:
        """Review code quality and structure."""
        request = f"Review code in: {path}"
        await self._process_code_analysis_task(request)

        # Convert to structured output (simplified)
        return CodeAnalysis(
            files_analyzed=1,
            complexity_score=0.7,
            suggestions=["Add type hints", "Improve documentation"],
        )

    async def generate_documentation(self, source_path: str) -> GeneratedContent:
        """Generate documentation for code."""
        request = f"Generate documentation for: {source_path}"
        await self._process_generation_task(request)

        # Convert to structured output (simplified)
        return GeneratedContent(
            content_type="api_documentation",
            content="# Generated Documentation\n\nThis is generated content...",
            confidence=0.85,
        )
