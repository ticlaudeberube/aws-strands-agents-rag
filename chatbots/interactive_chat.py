#!/usr/bin/env python3
"""Interactive Q&A chatbot using Strands RAG Agent."""

import logging
import sys
from pathlib import Path
from src.config.settings import get_settings
from src.agents.strands_rag_agent import StrandsRAGAgent

# Load environment variables from .env file (required for TAVILY_API_KEY and other secrets)
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_header():
    """Print welcome header."""
    print("\n" + "=" * 60)
    print("  AWS Strands Agents RAG - Interactive Chat")
    print("=" * 60)
    print("\nCommands:")
    print("  /quit or /exit  - Exit the chatbot")
    print("  /help           - Show this help message")
    print("  /collections    - List available collections")
    print("\nOtherwise, ask a question about the Milvus documentation.")
    print("-" * 60 + "\n")


def main():
    """Main chatbot loop."""
    # Load settings
    settings = get_settings()

    # Check Ollama availability
    logger.info("Initializing StrandsRAGAgent...")
    try:
        agent = StrandsRAGAgent(settings=settings)
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        sys.exit(1)

    if not agent.ollama_client.is_available():
        logger.error("✗ Ollama is not available")
        logger.error(f"  Please ensure Ollama is running at {settings.ollama_host}")
        sys.exit(1)

    logger.info("✓ Ollama is available")
    logger.info(f"✓ Milvus connected to {settings.milvus_host}:{settings.milvus_port}")
    logger.info(f"✓ Database: {settings.milvus_db_name}")

    # Default collection for queries
    collection_name = settings.ollama_collection_name

    print_header()

    # Chat loop
    try:
        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ["/quit", "/exit"]:
                    print("\nGoodbye! 👋\n")
                    break

                if user_input.lower() == "/help":
                    print_header()
                    continue

                if user_input.lower() == "/collections":
                    print(f"Using collection: {collection_name}")
                    print(f"Available databases: {settings.milvus_db_name}")
                    continue

                # Answer the question
                print("\nAssistant: ", end="", flush=True)
                try:
                    answer, sources = agent.answer_question(
                        collection_name=collection_name,
                        question=user_input,
                        top_k=5,
                    )
                    print(answer)
                    print()
                except Exception as e:
                    print(f"\n❌ Error answering question: {e}\n")
                    logger.error(f"Failed to answer: {e}")

            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋\n")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                print(f"❌ Error: {e}\n")

    finally:
        # Clean up resources
        agent.close()
        logger.info("Agent closed")


if __name__ == "__main__":
    main()
