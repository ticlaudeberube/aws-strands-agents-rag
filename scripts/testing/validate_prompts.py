#!/usr/bin/env python3
"""
Quality Assurance: Validate Agent Prompts Configuration
Prevents agent misconfiguration issues by validating prompts.py alignment.

Use Cases:
- Pre-deployment validation
- After prompt changes
- CI/CD pipeline integration
"""

import sys

try:
    from src.agents import prompts
    from src.agents.strands_graph_agent import StrandsGraphRAGAgent
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run from project root: python scripts/testing/validate_prompts.py")
    sys.exit(1)


def validate_prompts() -> bool:
    """Validate that prompts.py aligns with agent implementation."""
    print("=" * 80)
    print("✅ PROMPT VALIDATION")
    print("=" * 80)

    validation_passed = True
    issues = []

    # Check prompts module structure
    print("\n📋 Checking prompts module structure...")

    required_prompts = ["TOPIC_CHECKER_PROMPT", "SECURITY_CHECKER_PROMPT", "RAG_WORKER_PROMPT"]

    for prompt_name in required_prompts:
        if hasattr(prompts, prompt_name):
            prompt_value = getattr(prompts, prompt_name)
            if isinstance(prompt_value, str) and len(prompt_value.strip()) > 0:
                print(f"   ✅ {prompt_name}: Found ({len(prompt_value)} chars)")
            else:
                print(f"   ❌ {prompt_name}: Empty or invalid")
                issues.append(f"Prompt {prompt_name} is empty or not a string")
                validation_passed = False
        else:
            print(f"   ❌ {prompt_name}: Missing")
            issues.append(f"Missing required prompt: {prompt_name}")
            validation_passed = False

    # Check for placeholder patterns that should be replaced
    print("\n🔍 Checking for unresolved placeholders...")

    placeholder_patterns = ["{", "}", "TODO:", "FIXME:", "XXX:", "PLACEHOLDER", "[INSERT", "[TODO"]

    for prompt_name in required_prompts:
        if hasattr(prompts, prompt_name):
            prompt_value = getattr(prompts, prompt_name)
            if isinstance(prompt_value, str):
                for pattern in placeholder_patterns:
                    if pattern in prompt_value:
                        print(f"   🟡 {prompt_name}: Contains '{pattern}' - may be placeholder")
                        issues.append(
                            f"Prompt {prompt_name} contains potential placeholder: {pattern}"
                        )

    # Validate prompt content quality
    print("\n📝 Checking prompt content quality...")

    quality_checks = [
        ("length", lambda p: len(p.strip()) >= 50, "Prompt should be at least 50 characters"),
        (
            "instructions",
            lambda p: any(word in p.lower() for word in ["you are", "your role", "instructions"]),
            "Should contain role/instruction keywords",
        ),
        (
            "specific",
            lambda p: len(p.split()) >= 10,
            "Should contain specific guidance (10+ words)",
        ),
    ]

    for prompt_name in required_prompts:
        if hasattr(prompts, prompt_name):
            prompt_value = getattr(prompts, prompt_name)
            if isinstance(prompt_value, str):
                print(f"\n   Checking {prompt_name}:")

                for check_name, check_func, description in quality_checks:
                    try:
                        if check_func(prompt_value):
                            print(f"      ✅ {check_name}: Pass")
                        else:
                            print(f"      🟡 {check_name}: Warning - {description}")
                    except Exception as e:
                        print(f"      ❌ {check_name}: Error during check - {e}")

    # Check agent class integration
    print("\n🔧 Checking agent integration...")

    try:
        # Create agent instance to test integration
        agent = StrandsGraphRAGAgent()
        print("   ✅ Agent initialization: Success")

        # Check if agent has the expected structure
        expected_methods = [
            "answer_question",
            "_get_topic_checker",
            "_get_security_checker",
            "_get_rag_worker",
        ]

        for method_name in expected_methods:
            if hasattr(agent, method_name):
                print(f"   ✅ Method {method_name}: Found")
            else:
                print(f"   ❌ Method {method_name}: Missing")
                issues.append(f"Agent missing expected method: {method_name}")
                validation_passed = False

    except Exception as e:
        print(f"   ❌ Agent initialization: Failed - {e}")
        issues.append(f"Agent initialization failed: {e}")
        validation_passed = False

    # Check for consistency in prompt style
    print("\n🎨 Checking prompt style consistency...")

    if all(hasattr(prompts, name) for name in required_prompts):
        prompt_values = [getattr(prompts, name) for name in required_prompts]

        # Check for consistent instruction format
        instruction_patterns = ["You are", "Your role is", "Act as", "You must", "Always"]

        pattern_counts = {}
        for pattern in instruction_patterns:
            count = sum(1 for prompt in prompt_values if pattern in prompt)
            pattern_counts[pattern] = count

        print("   📊 Instruction patterns usage:")
        for pattern, count in pattern_counts.items():
            print(f"      '{pattern}': {count}/{len(prompt_values)} prompts")

    # Final validation summary
    print("\n" + "=" * 80)
    print("📊 VALIDATION SUMMARY")
    print("=" * 80)

    if validation_passed:
        print("🟢 ALL VALIDATIONS PASSED")
        print("✅ Prompts are properly configured for production use")
    else:
        print("🔴 VALIDATION ISSUES FOUND")
        print(f"❌ {len(issues)} issues need attention:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")

    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("=" * 80)

    recommendations = [
        "Run this validation after any prompt changes",
        "Include this script in CI/CD pipeline",
        "Test prompt changes with interactive chat before deployment",
        "Monitor agent responses for prompt effectiveness",
    ]

    for i, rec in enumerate(recommendations, 1):
        print(f"   {i}. {rec}")

    if not validation_passed:
        print("\n🚨 Fix issues before deploying to production!")

    return validation_passed


def main():
    """Main function."""
    success = validate_prompts()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
