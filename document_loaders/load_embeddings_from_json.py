import argparse
import json
import sys
from pathlib import Path

from tqdm import tqdm  # type: ignore[import-untyped]

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from document_loaders.core.tools import OpenSearchVectorDB
from document_loaders.local_settings import get_loader_settings

settings = get_loader_settings()
index_name = settings.opensearch_kb_index

vector_db = OpenSearchVectorDB(
    host=settings.opensearch_local_host,
    port=settings.opensearch_local_port,
)


def sync_embeddings(recreate=False):
    """Sync embeddings from JSON file into the OpenSearch KB index."""
    try:
        with open("./data/embeddings.json", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ Error: ./data/embeddings.json not found")
        print("   Please run: python document_loaders/load_docs_opensearch.py")
        return

    if not data:
        print("❌ No data to sync")
        return

    # Drop + recreate the index when requested, otherwise index into the
    # existing one.
    if recreate and vector_db.delete_index(index_name):
        print(f"Dropped existing index '{index_name}' (--recreate)")

    # Extract embeddings, texts, and metadata from JSON
    embeddings = [item["vector"] for item in data]
    texts = [item["text"] for item in data]
    metadata = [item.get("metadata", {}) for item in data]

    # Determine embedding dimension
    embedding_dim = len(embeddings[0]) if embeddings else settings.embedding_dim

    # Ensure index exists
    print(f"Ensuring index '{index_name}' with dimension {embedding_dim}...")
    vector_db.ensure_index(index_name, embedding_dim=embedding_dim)

    # Index embeddings
    print(f"Indexing {len(embeddings)} embeddings...")
    try:
        with tqdm(total=len(embeddings), desc="Syncing embeddings", ncols=80) as pbar:
            indexed = vector_db.index_documents(
                index_name=index_name,
                embeddings=embeddings,
                texts=texts,
                metadata=metadata,
            )
            pbar.update(len(embeddings))
        print(f"✅ Successfully synced {indexed} embeddings into index '{index_name}'")
    except Exception as e:
        print(f"❌ Error indexing embeddings: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync data/embeddings.json into OpenSearch.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the OpenSearch index before indexing.",
    )
    args = parser.parse_args()
    try:
        sync_embeddings(recreate=args.recreate)
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        sys.exit(1)
