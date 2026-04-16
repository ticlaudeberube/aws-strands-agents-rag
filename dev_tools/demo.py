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
from pathlib import Path

from dev_tools.mcp_server import CoreAgentMCPServer, IntegratedMCPServer
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


async def demo_mcp_server():
    """Demonstrate MCP server functionality."""
    print("\n🌐 MCP Server Demo")
    print("=" * 50)
    
    settings = Settings() 
    mcp_server = CoreAgentMCPServer(settings)
    
    # Show available tools
    tools = mcp_server.get_tools()
    print(f"Available Tools: {len(tools)}")
    for tool in tools[:5]:  # Show first 5 tools
        print(f"  - {tool['name']}: {tool['description'][:60]}...")
    
    # Show available resources
    resources = mcp_server.get_resources()
    print(f"\nAvailable Resources: {len(resources)}")
    for resource in resources:
        print(f"  - {resource['name']}: {resource['description']}")
    
    # Demonstrate tool invocation
    try:
        result = await mcp_server.invoke_tool(
            "analyze_files",
            {
                "path": "src/agents/",
                "file_pattern": "*.py",
                "recursive": False
            }
        )
        
        print(f"\n🛠️  Tool Invocation Result:")
        print(f"Status: {result.get('status')}")
        if result.get('status') == 'success':
            tool_result = result.get('result', {})
            print(f"Files Found: {tool_result.get('files_found', 0)}")
            print(f"Files Analyzed: {tool_result.get('files_analyzed', 0)}")
            
    except Exception as e:
        logger.error(f"MCP tool invocation failed: {e}")


async def demo_integrated_server():
    """Demonstrate integrated server with both RAG and Core agents."""
    print("\n🔗 Integrated Server Demo")
    print("=" * 50)
    
    settings = Settings()
    integrated = IntegratedMCPServer(settings)
    
    # Show combined capabilities
    all_tools = integrated.get_all_tools()
    all_resources = integrated.get_all_resources()
    
    print(f"Total Tools Available: {len(all_tools)}")
    print(f"Total Resources Available: {len(all_resources)}")
    
    # Show server status
    status = integrated.get_server_status()
    print(f"\n📊 Server Status:")
    print(f"RAG Server Tools: {status['rag_server']['tools']}")
    print(f"Core Server Tools: {status['core_server']['tools']}")
    print(f"Total Tools: {status['total_tools']}")
    
    # Show skills breakdown
    core_skills = status['core_server']['skills']
    print(f"\n🎯 Core Agent Skills:")
    for skill_name, skill_info in core_skills.items():
        print(f"  - {skill_name}: {skill_info['tool_count']} tools")


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
        await demo_mcp_server()
        await demo_integrated_server()
        await demo_direct_tool_access()
        
        print("\n✨ All demonstrations completed successfully!")
        
    except Exception as e:
        logger.error(f"Demonstration failed: {e}", exc_info=True)


if __name__ == "__main__":
    # Run the demonstration
    asyncio.run(main())