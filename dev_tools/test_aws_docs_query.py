
import os
import sys
from pathlib import Path

# Ensure workspace root is in PYTHONPATH for direct execution
WORKSPACE_ROOT = str(Path(__file__).parent.parent.resolve())
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from dev_tools.skills import aws_docs_query

if __name__ == "__main__":
    query = "What is Amazon S3?"
    result = aws_docs_query(query)
    print("AWS Docs Query Result:")
    print(result)
