"""Milvus vector database utilities."""

import json
import logging
from typing import Any

from pymilvus import MilvusClient  # type: ignore[import-untyped]


class MilvusVectorDB:
    """Wrapper for Milvus vector database operations with connection pooling."""

    def list_all_cached_questions(self, collection_name: str, limit: int = 100) -> list:
        """List all cached questions with full response data for GUI/API."""
        try:
            self.client.load_collection(collection_name=collection_name, db_name=self.db_name)
        except Exception:
            pass  # Already loaded or not needed
        results = self.client.query(
            collection_name=collection_name,
            db_name=self.db_name,
            output_fields=["id", "text", "metadata"],
            limit=limit,
        )
        out = []
        for entity in results or []:
            entity_id = entity.get("id")
            answer = entity.get("text", "")
            metadata = entity.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            question = metadata.get("question", "").strip()
            sources = metadata.get("sources", [])
            timing = metadata.get("timing", {})
            if question:
                out.append(
                    {
                        "id": str(entity_id),
                        "question": question,
                        "answer": answer,
                        "sources": sources,
                        "timing": timing,
                    }
                )
        return out

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db_name: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: int | None = None,
        pool_size: int | None = None,
    ):
        from src.config.settings import get_settings

        settings = get_settings()
        host = host or settings.milvus_host
        port = port or settings.milvus_port
        db_name = db_name or settings.milvus_db_name
        user = user or settings.milvus_user
        password = password or settings.milvus_password
        timeout = timeout or settings.milvus_timeout
        pool_size = pool_size or settings.milvus_pool_size

        uri = f"http://{host}:{port}"
        self.host = host
        self.port = port
        self.timeout = timeout
        self.pool_size = pool_size

        try:
            self.client = MilvusClient(
                uri=uri,
                user=user,
                password=password,
                pool_size=pool_size,
                db_name=db_name,
            )
            logging.info(f"Connected to Milvus at {uri} with db_name={db_name}")
        except Exception as e:
            logging.error(f"Cannot connect to Milvus at {uri}: {e}")
            raise RuntimeError(
                f"Milvus connection failed at {host}:{port}. Make sure Milvus is running."
            ) from e

        self.db_name = db_name
        # Optionally: ensure database exists, etc.

    def create_collection(
        self,
        collection_name: str,
        embedding_dim: int | None = None,
        index_type: str | None = None,
        metric_type: str | None = None,
    ) -> bool:
        """Create a collection for storing embeddings with optimal indexing."""
        from src.config.settings import get_settings

        settings = get_settings()
        if embedding_dim is None:
            embedding_dim = 768  # Default fallback if not provided
        if index_type is None:
            index_type = settings.milvus_index_type
        if metric_type is None:
            metric_type = settings.milvus_metric_type

        try:
            if collection_name in self.client.list_collections(db_name=self.db_name):
                logging.info(f"Collection {collection_name} already exists")
                return False

            index_params: dict[str, Any] = {
                "metric_type": metric_type,
                "index_type": index_type,
            }
            if index_type == "HNSW":
                index_params["params"] = {
                    "M": settings.milvus_hnsw_m,
                    "efConstruction": settings.milvus_hnsw_ef_construction,
                }
            elif index_type == "IVF_FLAT":
                index_params["params"] = {
                    "nlist": settings.milvus_ivf_nlist,
                }

            self.client.create_collection(
                collection_name=collection_name,
                dimension=embedding_dim,
                metric_type=metric_type,
                primary_field_name="id",
                vector_field_name="vector",
                id_type="int",
                db_name=self.db_name,
                index_params=index_params,
            )
            logging.info(f"Created collection: {collection_name} with {index_type} index")
            return True
        except Exception as e:
            logging.error(f"Failed to create collection: {e}")
            raise

    def search(
        self, collection_name: str, query_embedding: list[float], limit: int = 5
    ) -> list[dict]:
        """Search for similar embeddings in the collection."""
        try:
            self.client.load_collection(collection_name=collection_name, db_name=self.db_name)
        except Exception:
            pass  # Already loaded or not needed

        results = self.client.search(
            collection_name=collection_name,
            data=[query_embedding],
            limit=limit,
            output_fields=["id", "text", "metadata"],
            db_name=self.db_name,
        )
        # results is a list of lists (one per query)
        if not results or not results[0]:
            return []
        out = []
        for hit in results[0]:
            meta = hit.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            out.append(
                {
                    "id": hit.get("id"),
                    "text": hit.get("text", ""),
                    "metadata": meta,
                    "distance": hit.get("score", 0.0),
                }
            )
        return out

    def insert_embeddings(
        self,
        collection_name: str,
        embeddings: list[list[float]],
        texts: list[str],
        metadata: list[dict[str, Any]],
    ) -> None:
        """Insert embeddings and associated data into the collection."""
        import random
        import time

        data = []
        base_id = int(time.time() * 1000) % (2**31 - 1)
        for idx, (embedding, text, item_metadata) in enumerate(zip(embeddings, texts, metadata)):
            document_name = item_metadata.get("document_name") or item_metadata.get("filename", "")
            source = item_metadata.get("source", "unknown")
            metadata_json = json.dumps(item_metadata)
            unique_id = base_id + idx + random.randint(1, 999)
            unique_id = abs(unique_id) % (2**31 - 1)
            if unique_id == 0:
                unique_id = 1
            data.append(
                {
                    "id": unique_id,
                    "vector": embedding,
                    "text": text,
                    "document_name": document_name,
                    "source": source,
                    "metadata": metadata_json,
                }
            )
        logging.info(f"Inserting {len(data)} embeddings into '{collection_name}'")
        result = self.client.insert(
            collection_name=collection_name, data=data, db_name=self.db_name
        )
        try:
            self.client.flush(collection_name=collection_name, db_name=self.db_name)
            logging.info(
                f"Successfully inserted and flushed {len(data)} embeddings into '{collection_name}'"
            )
        except Exception as e:
            logging.error(f"Flush failed for '{collection_name}': {e}")

    def list_collections(self) -> list[str]:
        """List all collections in the database."""
        try:
            collections = self.client.list_collections(db_name=self.db_name)
            return list(collections) if collections else []
        except Exception as e:
            logging.error(f"Failed to list collections: {e}")
            return []
