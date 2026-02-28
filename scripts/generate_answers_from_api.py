#!/usr/bin/env python3
"""Generate answers.json from common_questions by querying the API.

This script:
1. Reads questions from config/common_questions.json
2. Queries the API to get answers for each question
3. Saves Q&A pairs to data/answers.json for later cache loading
"""

import json
import os
import sys
import time
import logging
import requests
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration - read API_PORT from .env or default to 8000
API_PORT = os.getenv("API_PORT", "8000")
API_HOST = f"http://localhost:{API_PORT}"
API_ENDPOINT = f"{API_HOST}/v1/chat/completions?bypass_cache=true"  # Bypass cache for fresh answers
HEALTH_ENDPOINT = f"{API_HOST}/health"

def check_api_health():
    """Check if API is running and healthy."""
    try:
        response = requests.get(HEALTH_ENDPOINT, timeout=5)
        if response.status_code == 200:
            return True
    except requests.exceptions.RequestException:
        pass
    return False

def load_common_questions():
    """Load questions from config/common_questions.json"""
    try:
        with open("./config/common_questions.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            questions = data.get("common_questions", [])
            logger.info(f"✓ Loaded {len(questions)} questions from config/common_questions.json")
            for i, q in enumerate(questions, 1):
                logger.debug(f"  {i}. {q}")
            return questions
    except FileNotFoundError:
        logger.error("❌ Error: ./config/common_questions.json not found")
        return []

def query_api_for_answer(question: str) -> str:
    """Query API to get answer for a question.
    
    Args:
        question: The question to ask
        
    Returns:
        The answer from the API, or empty string if failed
    """
    try:
        logger.info(f"Querying API: {question}")
        
        payload = {
            "messages": [
                {"role": "user", "content": question}
            ],
            "model": "rag-agent"
        }
        
        logger.debug(f"Request payload: {json.dumps(payload)}")
        
        response = requests.post(
            API_ENDPOINT,
            json=payload,
            timeout=120  # LLM generation can take time
        )
        
        if response.status_code == 200:
            data = response.json()
            # Extract answer from response
            if data.get("choices") and len(data["choices"]) > 0:
                answer = data["choices"][0].get("message", {}).get("content", "")
                logger.info(f"✓ Received answer ({len(answer)} chars): {answer[:100]}...")
                return answer.strip()
        else:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return ""
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout: LLM generation took >120s")
        return ""
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        return ""
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse API response: {e}")
        return ""

def generate_answers():
    """Generate answers.json from common questions."""
    
    # Check API health
    logger.info("Checking API health...")
    if not check_api_health():
        logger.error(f"❌ API not running at {API_HOST}")
        logger.error(f"   Please start: python api_server.py")
        return
    
    logger.info(f"✓ API is healthy\n")
    
    # Load questions
    questions = load_common_questions()
    if not questions:
        logger.error("❌ No questions found in config/common_questions.json")
        return
    
    logger.info("=" * 70)
    logger.info(f"Starting to generate answers for {len(questions)} questions using API")
    logger.info("=" * 70)
    
    qa_pairs = []
    
    for i, question in enumerate(questions, 1):
        start_time = time.time()
        answer = query_api_for_answer(question)
        elapsed = time.time() - start_time
        
        if answer:
            logger.info(f"{i}. Answer generated in {elapsed:.1f}s - {len(answer)} characters")
            qa_pairs.append({
                "question": question,
                "answer": answer,
                "collection": "milvus_rag_collection"
            })
        else:
            logger.warning(f"{i}. Failed to get answer for: {question}")
    
    if not qa_pairs:
        logger.error("❌ No answers generated")
        return
    
    # Save to answers.json
    output_data = {
        "qa_pairs": qa_pairs,
        "description": "Pre-generated question-answer pairs for response cache",
        "generated_count": len(qa_pairs),
        "total_expected": len(questions),
        "version": "1.0",
        "usage": "Run: python document-loaders/sync_answers_cache.py to load into response_cache"
    }
    
    output_path = Path("./data/answers.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info("\n" + "=" * 70)
    logger.info(f"✓ Generated answers.json")
    logger.info(f"  Location: {output_path}")
    logger.info(f"=" * 70)
    
    # Calculate and log cache statistics
    total_answers_cached = len(qa_pairs)
    total_chars_cached = sum(len(qa.get("answer", "")) for qa in qa_pairs)
    avg_answer_length = total_chars_cached / total_answers_cached if total_answers_cached > 0 else 0
    
    logger.info(f"\nCache Statistics:")
    logger.info(f"  ✓ Q&A pairs generated: {total_answers_cached}/{len(questions)}")
    logger.info(f"  ✓ Total characters cached: {total_chars_cached:,}")
    logger.info(f"  ✓ Average answer length: {avg_answer_length:.0f} characters")
    
    if len(qa_pairs) < len(questions):
        failed_count = len(questions) - len(qa_pairs)
        logger.warning(f"  ⚠️  Failed questions: {failed_count}")
    else:
        logger.info(f"  ✓ All questions cached successfully!")
    
    logger.info(f"\nNext step to load into response cache:")
    logger.info(f"  python document-loaders/sync_answers_cache.py")

if __name__ == "__main__":
    generate_answers()
