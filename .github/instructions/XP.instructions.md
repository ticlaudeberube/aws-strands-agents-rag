# XP (Extreme Programming) Patterns & Best Practices

This guide outlines the Extreme Programming (XP) principles and best practices used in the AWS Strands Agents RAG project.

## Core XP Principles

### 1. Test-Driven Development (TDD)
- Write tests before implementation
- Maintain high code coverage (aim for >80%)
- Use pytest for all Python tests
- Follow AAA pattern: Arrange, Act, Assert
- Run tests frequently during development

### 2. Continuous Integration
- Commit code frequently (multiple times per day)
- Automated testing on every commit
- Keep build times short (<10 minutes)
- Fix broken builds immediately
- All tests must pass before merging

### 3. Refactoring
- Refactor continuously, not just at the end
- Keep functions small and focused (single responsibility)
- Extract functions when logic gets complex
- Use automated refactoring tools for import improvements
- Update tests alongside refactoring

### 4. Pair Programming Practices
- Driver and navigator roles (switch frequently)
- Real-time code review during pairing
- Ensures knowledge sharing and code quality
- Document pairing sessions in PR descriptions

### 5. Simple Design
- Implement only what's needed now (YAGNI - You Aren't Gonna Need It)
- Avoid over-engineering solutions
- Choose clarity over cleverness
- Use existing patterns and utilities from codebase

### 6. Code Standards & Naming
- Use descriptive, intention-revealing names
- Avoid abbreviations unless widely known
- Consistent naming across modules
- Follow Python PEP 8 style guide
- Use type hints for better code clarity

### 7. Small Releases
- Deploy small, manageable changes
- Release frequently (weekly/bi-weekly when possible)
- Feature flags for gradual rollout
- Easy rollback mechanism

### 8. Collective Code Ownership
- No single owner for any specific part
- Any developer can modify any code
- Documentation must be clear for smooth handoffs
- Review changes across modules

### 9. On-Site Customer / Product Owner
- Keep requirements clear and documented
- Regular feedback cycles
- Handle ambiguity by discussing with stakeholders
- Update documentation when requirements change

## Project-Specific XP Guidelines

When contributing to the AWS Strands Agents RAG project:

- **Keep agent implementations modular and testable** - RAG agents should have clear separation of concerns
- **Document RAG pipeline steps clearly** - For team understanding and knowledge sharing
- **Use feature branches with descriptive names** - Makes intent clear for code reviewers
- **Write meaningful commit messages** - Include both what and why you changed
- **Ensure comprehensive test coverage before refactoring** - Especially for critical RAG components
- **Reference Milvus documentation** during implementation reviews - Located in `document-loaders/milvus_docs/en/`
- **Update documentation when requirements change** - Keep setup instructions and error messages up-to-date

## Helpful Commands

```bash
# Run tests
pytest

# Run tests with coverage report
pytest --cov

# Document loaders
python document-loaders/load_milvus_docs_ollama.py

# Interactive chat
python chatbots/interactive_chat.py

# API server
python api_server.py
```

## Further Reading

- [Development Guide](../../docs/DEVELOPMENT.md) - Project development workflow
- [Getting Started](../../docs/GETTING_STARTED.md) - Setup and initialization
- [Architecture Overview](../../docs/ARCHITECTURE.md) - System design and components
