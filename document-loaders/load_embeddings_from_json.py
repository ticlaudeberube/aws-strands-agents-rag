import json
import sys
from pathlib import Path
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import get_settings
from src.tools import MilvusVectorDB

settings = get_settings()
collection_name = settings.ollama_collection_name
db_name = settings.loader_milvus_db_name

vector_db = MilvusVectorDB(
    host=settings.milvus_host,
    port=settings.milvus_port,
    db_name=db_name,
)


def sync_embeddings():
    """Sync embeddings from JSON file into Milvus collection"""
    try:
        with open("./data/embeddings.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ Error: ./data/embeddings.json not found")
        print("   Please run: python document-loaders/load_milvus_docs_ollama.py")
        return

    if not data:
        print("❌ No data to sync")
        return

    # Check if collection exists
    existing_collections = vector_db.list_collections()

    if collection_name in existing_collections:
        print(f"Collection '{collection_name}' already exists.")
        choice = input("Do you want to (o)verwrite or (a)bort? [o/a]: ").lower().strip()

        if choice == "a":
            print("Sync aborted by user.")
            return
        elif choice == "o":
            print(f"Dropping collection '{collection_name}'...")
            vector_db.delete_collection(collection_name)

    # Extract embeddings, texts, and metadata from JSON
    embeddings = [item["vector"] for item in data]
    texts = [item["text"] for item in data]
    metadata = [item.get("metadata", {}) for item in data]

    # Determine embedding dimension
    embedding_dim = len(embeddings[0]) if embeddings else 384

    # Create collection
    print(f"Creating collection '{collection_name}' with dimension {embedding_dim}...")
    vector_db.create_collection(
        collection_name=collection_name,
        embedding_dim=embedding_dim,
    )

    # Insert embeddings
    print(f"Inserting {len(embeddings)} embeddings...")
    try:
        with tqdm(total=len(embeddings), desc="Syncing embeddings", ncols=80) as pbar:
            vector_db.insert_embeddings(
                collection_name=collection_name,
                embeddings=embeddings,
                texts=texts,
                metadata=metadata,
            )
            pbar.update(len(embeddings))
        print(
            f"✅ Successfully synced {len(embeddings)} embeddings into collection '{collection_name}'"
        )
    except Exception as e:
        print(f"❌ Error inserting embeddings: {e}")
        raise


if __name__ == "__main__":
    try:
        sync_embeddings()
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        sys.exit(1)
