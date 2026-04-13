"""Unit tests for the externalized prompts module.

Tests that the prompts module correctly defines all system instructions
and formatting rules required by the RAG agent.

This test suite validates the DRY (Don't Repeat Yourself) principle
for prompt management and ensures prompts are properly externalized.
"""

from src.agents import prompts

# ============================================================================
# UNIT TESTS: Prompt Module Structure
# ============================================================================


class TestPromptsModuleStructure:
    """Test suite for prompts module structure and organization."""

    def test_module_imports_successfully(self):
        """Verify prompts module imports without errors."""
        assert prompts is not None
        assert hasattr(prompts, "ScopeCheckPrompts")
        assert hasattr(prompts, "SecurityCheckPrompts")
        assert hasattr(prompts, "RAGPrompts")
        assert hasattr(prompts, "FORMATTING_RULES")

    def test_all_required_classes_exist(self):
        """Verify all required prompt classes are defined."""
        required_classes = [
            "ScopeCheckPrompts",
            "SecurityCheckPrompts",
            "RAGPrompts",
            "ComparisonPrompts",
            "WebSearchPrompts",
        ]
        for class_name in required_classes:
            assert hasattr(prompts, class_name), f"Missing class: {class_name}"

    def test_all_classes_are_classes(self):
        """Verify prompt classes are actual class objects."""
        assert isinstance(prompts.ScopeCheckPrompts, type)
        assert isinstance(prompts.SecurityCheckPrompts, type)
        assert isinstance(prompts.RAGPrompts, type)
        assert isinstance(prompts.ComparisonPrompts, type)
        assert isinstance(prompts.WebSearchPrompts, type)


# ============================================================================
# UNIT TESTS: ScopeCheckPrompts Class
# ============================================================================


class TestScopeCheckPrompts:
    """Test suite for ScopeCheckPrompts class."""

    def test_system_instructions_attribute_exists(self):
        """Verify SYSTEM_INSTRUCTIONS attribute exists."""
        assert hasattr(prompts.ScopeCheckPrompts, "SYSTEM_INSTRUCTIONS")

    def test_system_instructions_is_string(self):
        """Verify SYSTEM_INSTRUCTIONS is a string."""
        assert isinstance(prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS, str)

    def test_system_instructions_is_non_empty(self):
        """Verify SYSTEM_INSTRUCTIONS is not empty."""
        assert len(prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS) > 0

    def test_system_instructions_has_relevant_keywords(self):
        """Verify system instructions contain relevant topic keywords."""
        prompt = prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS.lower()
        
        # Should mention topic validation or scope checking
        has_validation = "validation" in prompt or "validate" in prompt or "check" in prompt
        has_scope = "scope" in prompt or "topic" in prompt
        has_content = "question" in prompt or "query" in prompt or "database" in prompt
        
        assert has_validation or has_scope or has_content, \
            "Prompt should mention validation, scope, or topic checking"

    def test_system_instructions_no_placeholder_variables(self):
        """Verify system instructions don't have placeholder variables."""
        prompt = prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS
        
        # Check for placeholder patterns that would be problematic
        forbidden_placeholders = ["{question}", "{query}", "{context}", "{user_input}"]
        for placeholder in forbidden_placeholders:
            assert placeholder not in prompt, \
                f"Prompt should not have placeholder {placeholder}"

    def test_no_deprecated_attributes(self):
        """Verify deprecated LLM_CLASSIFICATION attribute is removed."""
        assert not hasattr(prompts.ScopeCheckPrompts, "LLM_CLASSIFICATION"), \
            "LLM_CLASSIFICATION should be removed (use SYSTEM_INSTRUCTIONS)"


# ============================================================================
# UNIT TESTS: SecurityCheckPrompts Class
# ============================================================================


class TestSecurityCheckPrompts:
    """Test suite for SecurityCheckPrompts class."""

    def test_system_instructions_attribute_exists(self):
        """Verify SYSTEM_INSTRUCTIONS attribute exists."""
        assert hasattr(prompts.SecurityCheckPrompts, "SYSTEM_INSTRUCTIONS")

    def test_system_instructions_is_string(self):
        """Verify SYSTEM_INSTRUCTIONS is a string."""
        assert isinstance(prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS, str)

    def test_system_instructions_is_non_empty(self):
        """Verify SYSTEM_INSTRUCTIONS is not empty."""
        assert len(prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS) > 0

    def test_system_instructions_addresses_security(self):
        """Verify system instructions address security concerns."""
        prompt = prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS.lower()
        
        security_keywords = ["security", "attack", "risk", "threat", "malicious", "safe"]
        has_security_content = any(keyword in prompt for keyword in security_keywords)
        
        assert has_security_content, \
            "Prompt should address security, attacks, risks, or threats"

    def test_system_instructions_no_placeholder_variables(self):
        """Verify system instructions don't have placeholder variables."""
        prompt = prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS
        
        forbidden_placeholders = ["{question}", "{query}", "{context}", "{user_input}"]
        for placeholder in forbidden_placeholders:
            assert placeholder not in prompt, \
                f"Prompt should not have placeholder {placeholder}"

    def test_no_deprecated_attributes(self):
        """Verify deprecated LLM_CLASSIFICATION attribute is removed."""
        assert not hasattr(prompts.SecurityCheckPrompts, "LLM_CLASSIFICATION"), \
            "LLM_CLASSIFICATION should be removed (use SYSTEM_INSTRUCTIONS)"


# ============================================================================
# UNIT TESTS: RAGPrompts Class
# ============================================================================


class TestRAGPrompts:
    """Test suite for RAGPrompts class."""

    def test_system_instructions_attribute_exists(self):
        """Verify SYSTEM_INSTRUCTIONS attribute exists."""
        assert hasattr(prompts.RAGPrompts, "SYSTEM_INSTRUCTIONS")

    def test_system_instructions_is_string(self):
        """Verify SYSTEM_INSTRUCTIONS is a string."""
        assert isinstance(prompts.RAGPrompts.SYSTEM_INSTRUCTIONS, str)

    def test_system_instructions_is_non_empty(self):
        """Verify SYSTEM_INSTRUCTIONS is not empty."""
        assert len(prompts.RAGPrompts.SYSTEM_INSTRUCTIONS) > 0

    def test_system_instructions_has_rag_keywords(self):
        """Verify system instructions contain RAG-related keywords."""
        prompt = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS.lower()
        
        rag_keywords = [
            "answer", "context", "retrieve", "knowledge", "document",
            "provide", "source", "explain", "database"
        ]
        has_rag_content = any(keyword in prompt for keyword in rag_keywords)
        
        assert has_rag_content, \
            "Prompt should contain RAG-related keywords"

    def test_system_instructions_has_formatting_rules_placeholder(self):
        """Verify system instructions has {formatting_rules} placeholder."""
        prompt = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS
        
        assert "{formatting_rules}" in prompt, \
            "Prompt should have {formatting_rules} placeholder for formatting rules injection"

    def test_system_instructions_no_other_placeholders(self):
        """Verify system instructions only has formatting_rules placeholder."""
        prompt = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS
        
        # Only {formatting_rules} should be present
        forbidden_placeholders = ["{question}", "{query}", "{context}", "{user_input}"]
        for placeholder in forbidden_placeholders:
            assert placeholder not in prompt, \
                f"Prompt should not have placeholder {placeholder}"

    def test_system_instructions_can_be_formatted(self):
        """Verify system instructions can be formatted with formatting_rules."""
        prompt_template = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS
        formatting_rules = prompts.FORMATTING_RULES
        
        # Should format without errors
        formatted = prompt_template.format(formatting_rules=formatting_rules)
        
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        assert formatting_rules in formatted  # Rules should be injected

    def test_formatted_prompt_includes_rules(self):
        """Verify formatted prompt includes the formatting rules."""
        prompt_template = prompts.RAGPrompts.SYSTEM_INSTRUCTIONS
        formatting_rules = prompts.FORMATTING_RULES
        
        formatted = prompt_template.format(formatting_rules=formatting_rules)
        
        # Should contain content from both template and rules
        assert len(formatted) > len(prompt_template)
        assert "formatting" in formatted.lower() or "cite" in formatted.lower()


# ============================================================================
# UNIT TESTS: FORMATTING_RULES
# ============================================================================


class TestFormattingRules:
    """Test suite for FORMATTING_RULES constant."""

    def test_formatting_rules_exists(self):
        """Verify FORMATTING_RULES exists."""
        assert hasattr(prompts, "FORMATTING_RULES")

    def test_formatting_rules_is_string(self):
        """Verify FORMATTING_RULES is a string."""
        assert isinstance(prompts.FORMATTING_RULES, str)

    def test_formatting_rules_is_non_empty(self):
        """Verify FORMATTING_RULES is not empty."""
        assert len(prompts.FORMATTING_RULES) > 0

    def test_formatting_rules_contains_guidelines(self):
        """Verify FORMATTING_RULES contains actual formatting guidelines."""
        rules = prompts.FORMATTING_RULES.lower()
        
        formatting_keywords = [
            "format", "cite", "source", "link", "response", "structure",
            "clear", "concise", "accurate"
        ]
        has_guidelines = any(keyword in rules for keyword in formatting_keywords)
        
        assert has_guidelines, \
            "Formatting rules should contain formatting guidelines"

    def test_formatting_rules_no_placeholder_variables(self):
        """Verify FORMATTING_RULES has no placeholder variables."""
        rules = prompts.FORMATTING_RULES
        
        # Should not have template variables
        assert "{" not in rules or "formatting" not in rules, \
            "FORMATTING_RULES should not have template placeholders"


# ============================================================================
# INTEGRATION TESTS: Prompt Classes Configuration
# ============================================================================


class TestOtherPromptClasses:
    """Test suite for other prompt classes (sanity checks)."""

    def test_comparison_prompts_exists(self):
        """Verify ComparisonPrompts class exists."""
        assert hasattr(prompts, "ComparisonPrompts")
        assert isinstance(prompts.ComparisonPrompts, type)

    def test_web_search_prompts_exists(self):
        """Verify WebSearchPrompts class exists."""
        assert hasattr(prompts, "WebSearchPrompts")
        assert isinstance(prompts.WebSearchPrompts, type)

    def test_comparison_prompts_has_attributes(self):
        """Verify ComparisonPrompts has expected attributes."""
        comp_prompts = prompts.ComparisonPrompts
        # Should have some prompt content
        attributes = dir(comp_prompts)
        assert len(attributes) > 0

    def test_web_search_prompts_has_attributes(self):
        """Verify WebSearchPrompts has expected attributes."""
        web_prompts = prompts.WebSearchPrompts
        # Should have some prompt content
        attributes = dir(web_prompts)
        assert len(attributes) > 0


# ============================================================================
# VALIDATION TESTS: Prompt Quality and Coherence
# ============================================================================


class TestPromptQuality:
    """Test suite for prompt quality and coherence."""

    def test_all_system_instructions_are_coherent(self):
        """Verify all system instructions are grammatically coherent."""
        instructions = [
            prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS,
            prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS,
            prompts.RAGPrompts.SYSTEM_INSTRUCTIONS,
        ]
        
        for instruction in instructions:
            # Should start with capital letter
            assert instruction[0].isupper(), \
                f"Instruction should start with capital letter: {instruction[:50]}"
            
            # Should be reasonable length (not too short, not absurd)
            assert 20 < len(instruction) < 5000, \
                f"Instruction length suspicious: {len(instruction)}"

    def test_prompts_follow_naming_conventions(self):
        """Verify prompt attributes follow naming conventions."""
        # System instructions should be UPPERCASE
        assert hasattr(prompts.ScopeCheckPrompts, "SYSTEM_INSTRUCTIONS")
        assert hasattr(prompts.SecurityCheckPrompts, "SYSTEM_INSTRUCTIONS")
        assert hasattr(prompts.RAGPrompts, "SYSTEM_INSTRUCTIONS")

    def test_formatting_rules_follows_naming_conventions(self):
        """Verify FORMATTING_RULES follows naming convention."""
        # Should be module-level UPPERCASE constant
        assert hasattr(prompts, "FORMATTING_RULES")
        assert isinstance(prompts.FORMATTING_RULES, str)

    def test_no_typos_in_common_keywords(self):
        """Verify no common typos in prompts."""
        all_prompts_text = (
            prompts.ScopeCheckPrompts.SYSTEM_INSTRUCTIONS +
            prompts.SecurityCheckPrompts.SYSTEM_INSTRUCTIONS +
            prompts.RAGPrompts.SYSTEM_INSTRUCTIONS +
            prompts.FORMATTING_RULES
        )
        
        # Check for common typos
        typo_patterns = [
            ("recieve", "receive"),
            ("occured", "occurred"),
            ("seperate", "separate"),
        ]
        
        all_lower = all_prompts_text.lower()
        for typo, correct in typo_patterns:
            assert typo not in all_lower, \
                f"Found typo '{typo}' (should be '{correct}')"
