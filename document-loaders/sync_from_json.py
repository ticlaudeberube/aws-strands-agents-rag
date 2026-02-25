import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import get_settings
from core import get_client

settings = get_settings()
collection_name = settings.ollama_collection_name
db_name = settings.loader_milvus_db_name

client = get_client(db_name=db_name)

def sync_embeddings():
    """Sync embeddings from JSON file - adds, updates, and removes vectors"""
    with open("./data/embeddings.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not data:
        print("No data to sync")
        return
    
    if not client.has_collection(collection_name):
        dimension = len(data[0]['vector'])
        client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            metric_type="COSINE",
            consistency_level="Session",
        )
        print(f"Created collection: {collection_name}")
        existing_checksums = {}
    else:
        # Get existing data
        existing = client.query(
            collection_name=collection_name,
            filter="",
            output_fields=["id", "checksum"],
            limit=16384
        )
        existing_checksums = {item["id"]: item["checksum"] for item in existing}
    
    # Prepare data for upsert
    json_ids = {item["id"] for item in data}
    existing_ids = set(existing_checksums.keys())
    
    to_upsert = []
    new_count = 0
    updated_count = 0
    
    for item in data:
        item_id = item["id"]
        if item_id not in existing_checksums:
            new_count += 1
            to_upsert.append(item)
        elif existing_checksums[item_id] != item["checksum"]:
            updated_count += 1
            to_upsert.append(item)
    
    # Delete vectors not in JSON
    to_delete = existing_ids - json_ids
    if to_delete:
        client.delete(collection_name=collection_name, filter=f"id in {list(to_delete)}")
        print(f"Deleted {len(to_delete)} vectors")
    
    # Upsert new/changed vectors
    if to_upsert:
        client.upsert(collection_name=collection_name, data=to_upsert)
        print(f"Upserted {new_count} new, {updated_count} updated documents")
    else:
        print("No documents need updating")

if __name__ == "__main__":
    sync_embeddings()