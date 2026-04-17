"""Example usage of the Strands Core Agent for documentation and programming assistance.

This script demonstrates how to use the StrandsCoreAgent for various
documentation and code analysis tasks.

Location: This is the canonical demo file for StrandsCoreAgent.
Old Location: examples/core_agent_demo.py (removed due to outdated imports)

Usage:
    python dev_tools/demo.py
"""

import asyncio
import logging

from dev_tools.strands_core_agent import StrandsCoreAgent
from src.config import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_documentation_analysis():
    """Demonstrate documentation analysis capabilities."""
    print("\n🔍 Documentation Analysis Demo")
    print("=" * 50)
    
    settings = Settings()
    agent = StrandsCoreAgent(settings)
    
    # Analyze documentation structure
    try:
        result = await agent.process_request(
            "Analyze the documentation in the docs/ directory and suggest improvements"
        )
        
        print(f"Task Status: {result.get('status')}")
        print(f"Task Type: {result.get('task_type')}")
        print(f"Processing Time: {result.get('processing_time', 0):.2f}s")
        
        if result.get('status') == 'completed':
            print("\n📊 Analysis Results:")
            doc_result = result.get('documentation_result', {})
            print(f"Documentation Worker Response: {doc_result}")
            
    except Exception as e:
        logger.error(f"Documentation analysis failed: {e}")


async def demo_code_analysis():
    """Demonstrate code analysis capabilities."""
    print("\n🔧 Code Analysis Demo")  
    print("=" * 50)
    
    settings = Settings()
    agent = StrandsCoreAgent(settings)
    
    # Analyze code quality
    try:
        result = await agent.process_request(
            "Analyze the code quality in src/agents/strands_graph_agent.py and provide suggestions"
        )
        
        print(f"Task Status: {result.get('status')}")
        print(f"Task Type: {result.get('task_type')}")
        print(f"Processing Time: {result.get('processing_time', 0):.2f}s")
        
        if result.get('status') == 'completed':
            print("\n🎯 Analysis Results:")
            analysis_result = result.get('analysis_result', {})
            print(f"Code Analysis Worker Response: {analysis_result}")
            
    except Exception as e:
        logger.error(f"Code analysis failed: {e}")


async def demo_project_analysis():
    """Demonstrate project-wide analysis."""
    print("\n🏗️  Project Analysis Demo")
    print("=" * 50)
    
    settings = Settings()
    agent = StrandsCoreAgent(settings)
    
    # Analyze entire project
    try:
        result = await agent.process_request(
            "Provide a comprehensive analysis of this project's structure, code quality, and documentation"
        )
        
        print(f"Task Status: {result.get('status')}")
        print(f"Task Type: {result.get('task_type')}")
        print(f"Processing Time: {result.get('processing_time', 0):.2f}s")
        
        if result.get('status') == 'completed':
            print("\n📈 Project Analysis Results:")
            project_result = result.get('project_analysis', {})
            print(f"Code Analysis: {project_result.get('code_analysis', {})}")
            print(f"Documentation Analysis: {project_result.get('documentation_analysis', {})}")
            
    except Exception as e:
        logger.error(f"Project analysis failed: {e}")

async def demo_direct_tool_access():
    """Demonstrate direct tool access for specific tasks."""
    print("\n🎯 Direct Tool Access Demo")
    print("=" * 50)
    
    settings = Settings()
    agent = StrandsCoreAgent(settings)
    
    # Use tools directly
    try:
        # Analyze files
        print("📁 File Analysis:")
        file_result = agent.analyze_files(
            path="src/config/",
            file_pattern="*.py",
            recursive=True
        )
        print(f"Files analyzed: {file_result.get('files_analyzed', 0)}")
        
        # Generate documentation
        print("\n📝 Documentation Generation:")
        doc_result = agent.generate_documentation(
            source_path="src/config/settings.py",
            doc_type="api",
            output_format="markdown"
        )
        print(f"Generated docs for: {doc_result.get('source')}")
        print(f"Content preview: {doc_result.get('content', '')[:100]}...")
        
        # Analyze code quality
        print("\n⚡ Code Quality Analysis:")
        quality_result = agent.analyze_code_quality(
            file_path="api_server.py",
            analysis_type="comprehensive"
        )
        print(f"Analysis completed for: {quality_result.get('analysis', {}).get('file')}")
        print(f"Language: {quality_result.get('analysis', {}).get('language')}")
        print(f"Lines of code: {quality_result.get('analysis', {}).get('lines_of_code')}")
        
    except Exception as e:
        logger.error(f"Direct tool access failed: {e}")


def demo_validation_examples():
    """Show examples of task validation (no async needed)."""
    print("\n✅ Task Validation Examples")
    print("=" * 50)
    
    valid_requests = [
        "Analyze the documentation in docs/ directory",
        "Review code quality in src/agents/ folder",
        "Generate API documentation for api_server.py", 
        "Assess overall project structure and quality",
        "Detect design patterns in the codebase",
    ]
    
    invalid_requests = [
        "What's the weather today?",
        "Help me cook dinner",
        "Delete all my files",
        "Access my personal information",
        "Perform network attacks",
    ]
    
    print("Valid requests (would be accepted):")
    for i, request in enumerate(valid_requests, 1):
        print(f"  {i}. {request}")
    
    print("\nInvalid requests (would be rejected):")
    for i, request in enumerate(invalid_requests, 1):
        print(f"  {i}. {request}")


async def main():
    """Run all demonstrations."""
    print("🚀 Strands Core Agent Demonstration")
    print("=" * 60)
    
    try:
        # Show validation examples (sync)
        demo_validation_examples()
        
        # Run async demonstrations 
        await demo_documentation_analysis()
        await demo_code_analysis()
        await demo_project_analysis()
        await demo_direct_tool_access()
        
        print("\n✨ All demonstrations completed successfully!")
        
    except Exception as e:
        logger.error(f"Demonstration failed: {e}", exc_info=True)


if __name__ == "__main__":
    # Run the demonstration
    asyncio.run(main())