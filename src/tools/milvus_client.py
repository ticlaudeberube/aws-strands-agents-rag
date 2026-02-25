"""Milvus vector database utilities."""

from pymilvus import MilvusClient, Collection
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MilvusVectorDB:
    """Wrapper for Milvus vector database operations."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        db_name: str = "default",
        user: str = "root",
        password: str = "Milvus",
    ):
        """Initialize Milvus client.

        Args:
            host: Milvus server host
            port: Milvus server port
            db_name: Database name to use
            user: Milvus username (default: root)
            password: Milvus password (default: Milvus)
        """
        uri = f"http://{host}:{port}"
        self.host = host
        self.port = port
        
        try:
            # Try with authentication first
            self.client = MilvusClient(
                uri=uri,
                user=user,
                password=password,
            )
            logger.info(f"Connected to Milvus at {uri}")
        except ConnectionError as e:
            logger.error(f"❌ Cannot connect to Milvus at {uri}")
            logger.error(f"   Is Milvus running? Check: cd ../milvus-standalone && docker-compose ps")
            raise RuntimeError(f"Milvus connection failed at {host}:{port}. Make sure Milvus is running.") from e
        except Exception as auth_error:
            logger.warning(f"Auth failed, trying without credentials: {auth_error}")
            # Fall back to no auth
            try:
                self.client = MilvusClient(uri=uri)
                logger.info(f"Connected to Milvus at {uri} (without auth)")
            except Exception as e:
                logger.error(f"❌ Cannot connect to Milvus at {uri}")
                logger.error(f"   Is Milvus running? Check: cd ../milvus-standalone && docker-compose ps")
                raise RuntimeError(f"Milvus connection failed at {host}:{port}. Make sure Milvus is running.") from e
        
        self.db_name = db_name
        self._ensure_database()

    def _ensure_database(self):
        """Ensure the database exists."""
        try:
            databases = self.client.list_databases()
            if self.db_name not in databases:
                self.client.create_database(db_name=self.db_name)
                logger.info(f"Created database: {self.db_name}")
            # Switch to the correct database
            self.client.using_database(self.db_name)
            logger.info(f"Using database: {self.db_name}")
        except Exception as e:
            logger.warning(f"Could not verify/switch database: {e}")

    def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
    ) -> bool:
        """Create a collection for storing embeddings.

        Args:
            collection_name: Name of the collection to create
            embedding_dim: Dimension of embeddings

        Returns:
            True if collection was created, False if already exists
        """
        try:
            if collection_name in self.client.list_collections(db_name=self.db_name):
                logger.info(f"Collection {collection_name} already exists")
                return False

            # Use simple parameter-based schema for MilvusClient
            self.client.create_collection(
                collection_name=collection_name,
                dimension=embedding_dim,
                metric_type="COSINE",
                db_name=self.db_name,
            )
            logger.info(f"Created collection: {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise

    def insert_embeddings(
        self,
        collection_name: str,
        embeddings: List[List[float]],
        texts: List[str],
        metadata: List[Dict[str, Any]] = None,
    ) -> List[int]:
        """Insert embeddings and their associated text into collection.

        Args:
            collection_name: Name of the collection
            embeddings: List of embedding vectors
            texts: List of text documents
            metadata: Optional list of metadata dicts

        Returns:
            List of inserted IDs
        """
        try:
            if metadata is None:
                metadata = ["{}" for _ in texts]
            else:
                import json
                metadata = [json.dumps(m) for m in metadata]

            # Generate IDs (Milvus needs them even with auto_id)
            data = [
                {
                    "id": idx + 1,  # IDs start from 1
                    "vector": emb,  # Use 'vector' for MilvusClient API
                    "text": text,
                    "metadata": meta,
                }
                for idx, (emb, text, meta) in enumerate(zip(embeddings, texts, metadata))
            ]

            result = self.client.insert(
                collection_name=collection_name,
                data=data,
                db_name=self.db_name,
            )
            logger.info(f"Inserted {len(result['insert_count']) if isinstance(result.get('insert_count'), list) else result.get('insert_count', 0)} embeddings")
            return result.get("insert_count", [])

        except Exception as e:
            logger.error(f"Failed to insert embeddings: {e}")
            raise

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for similar embeddings.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            limit: Number of results to return

        Returns:
            List of search results with text and scores
        """
        try:
            results = self.client.search(
                collection_name=collection_name,
                data=[query_embedding],
                db_name=self.db_name,
                anns_field="vector",  # Use 'vector' for MilvusClient API
                limit=limit,
                output_fields=["text", "metadata"],
            )

            # Process results
            processed_results = []
            for result_group in results:
                for result in result_group:
                    processed_results.append({
                        "text": result.get("entity", {}).get("text", ""),
                        "metadata": result.get("entity", {}).get("metadata", "{}"),
                        "score": result.get("distance", 0),
                    })

            return processed_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if successful
        """
        try:
            self.client.drop_collection(
                collection_name=collection_name,
                db_name=self.db_name,
            )
            logger.info(f"Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            raise

    def list_collections(self) -> List[str]:
        """List all collections in the database.

        Returns:
            List of collection names
        """
        try:
            return self.client.list_collections(db_name=self.db_name)
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
