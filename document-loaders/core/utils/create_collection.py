import sys
from core import create_collection
if __name__ == "__main__":
    collection: str = sys.argv[1] if len(sys.argv) > 1 else None # type: ignore
    create_collection(collection)