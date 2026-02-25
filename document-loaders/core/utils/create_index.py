import sys
from pymilvus import MilvusClient, DataType
from dotenv import load_dotenv
load_dotenv()

from core import get_client

def create_index(_collection_name = "hello_world_collection"):
    # Constants
    COLLECTION_NAME: str = _collection_name
    VECTOR_DIM: int = 5
    MAX_TEXT_LENGTH: int = 65535
    INDEX_NAME="vector"

    # Optimized parameters for Docker Desktop
    NLIST_PARAM: int = 64  # Reduced for smaller datasets
    M_PARAM: int = 16      # HNSW connectivity
    EF_CONSTRUCTION: int = 200  # Build quality
    EF_SEARCH: int = 64    # Search quality vs speed

    client: MilvusClient = get_client()

    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=True,
    )

    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=MAX_TEXT_LENGTH)
    schema.add_field(field_name="metadata", datatype=DataType.JSON)

    index_params = MilvusClient.prepare_index_params()

    # Option 1: HNSW (Recommended for Docker Desktop)
    index_params.add_index(
        field_name="vector",
        metric_type="COSINE",
        index_type="HNSW",
        index_name=INDEX_NAME,
        params={
            "M": M_PARAM,
            "efConstruction": EF_CONSTRUCTION
        }
    )

    # Option 2: IVF_FLAT (Uncomment to use instead)
    # index_params.add_index(
    #     field_name="vector",
    #     metric_type="COSINE",
    #     index_type="IVF_FLAT",
    #     index_name=INDEX_NAME,
    #     params={"nlist": NLIST_PARAM}
    # )

    # Option 3: FLAT (For very small datasets < 10k vectors)
    # index_params.add_index(
    #     field_name="vector",
    #     metric_type="COSINE",
    #     index_type="FLAT",
    #     index_name=INDEX_NAME
    # )

    # Check if index already exists
    try:
        indexes = client.list_indexes(collection_name=COLLECTION_NAME)
        if INDEX_NAME in indexes:
            print(f"Index '{INDEX_NAME}' already exists on collection: {COLLECTION_NAME}")
            response = input("Do you want to remove the existing index and create a new one? (y/n): ").lower().strip()
            if response not in ['y', 'yes']:
                print("Index creation cancelled.")
                return
    except Exception:
        pass

    # Unload (release) collection before dropping index
    try:
        client.release_collection(collection_name=COLLECTION_NAME)
        print(f"Unloaded (released) collection: {COLLECTION_NAME}")
    except Exception:
        pass  # Collection might not be loaded

    # Drop existing index if it exists
    try:
        client.drop_index(collection_name=COLLECTION_NAME, index_name=INDEX_NAME)
        print(f"Dropped existing index '{INDEX_NAME}' on collection: {COLLECTION_NAME}")
    except Exception:
        pass  # Index might not exist

    try:
        client.create_index(
            collection_name=COLLECTION_NAME,
            index_params=index_params,
            sync=False
        )
        print(f"Index created for collection: {COLLECTION_NAME}")
        
        # Reload collection after creating index
        client.load_collection(collection_name=COLLECTION_NAME)
        print(f"Reloaded collection: {COLLECTION_NAME}")
        
    except Exception as e:
        print(f"Error creating index: {e}")
        exit(1)

if __name__ == "__main__":
    name: str = sys.argv[1] if len(sys.argv) > 1 else None # type: ignore
    create_index(name)