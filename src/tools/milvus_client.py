"""Milvus vector database utilities."""

from pymilvus import MilvusClient
from typing import List, Optional, Dict, Any
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class MilvusVectorDB:
    """Wrapper for Milvus vector database operations with connection pooling."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        db_name: str = "default",
        user: str = "root",
        password: str = "Milvus",
        timeout: int = 30,
        pool_size: int = 10,
    ):
        """Initialize Milvus client with connection pooling.

        Args:
            host: Milvus server host
            port: Milvus server port
            db_name: Database name to use
            user: Milvus username (default: root)
            password: Milvus password (default: Milvus)
            timeout: Request timeout in seconds
            pool_size: Connection pool size (not directly supported by MilvusClient, for future use)
        """
        uri = f"http://{host}:{port}"
        self.host = host
        self.port = port
        self.timeout = timeout
        self.pool_size = pool_size
        
        try:
            # Try with authentication first
            self.client = MilvusClient(
                uri=uri,
                user=user,
                password=password,
                pool_size=pool_size,
            )
            logger.info(f"Connected to Milvus at {uri}")
        except ConnectionError as e:
            logger.error(f"❌ Cannot connect to Milvus at {uri}")
            logger.error("   Is Milvus running? Check: cd docker && docker-compose ps")
            raise RuntimeError(f"Milvus connection failed at {host}:{port}. Make sure Milvus is running.") from e
        except Exception as auth_error:
            logger.warning(f"Auth failed, trying without credentials: {auth_error}")
            # Fall back to no auth
            try:
                self.client = MilvusClient(uri=uri, pool_size=pool_size)
                logger.info(f"Connected to Milvus at {uri} (without auth)")
            except Exception as e:
                logger.error(f"❌ Cannot connect to Milvus at {uri}")
                logger.error("   Is Milvus running? Check: cd docker && docker-compose ps")
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
        index_type: str = "HNSW",
        metric_type: str = "COSINE",
    ) -> bool:
        """Create a collection for storing embeddings with optimal indexing.

        Args:
            collection_name: Name of the collection to create
            embedding_dim: Dimension of embeddings
            index_type: Type of index (HNSW, IVF_FLAT, FLAT)
            metric_type: Similarity metric (COSINE, L2, IP)

        Returns:
            True if collection was created, False if already exists
        """
        try:
            if collection_name in self.client.list_collections(db_name=self.db_name):
                logger.info(f"Collection {collection_name} already exists")
                return False

            # Create collection with explicit index parameters (optimized for performance)
            index_params = {
                "metric_type": metric_type,
                "index_type": index_type,
            }
            
            # Set index-specific parameters
            if index_type == "HNSW":
                index_params["params"] = {
                    "M": 30,  # Maximum number of connections for each element
                    "efConstruction": 200,  # Size of dynamic list for construction
                }
            elif index_type == "IVF_FLAT":
                index_params["params"] = {
                    "nlist": 128,  # Number of clusters
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
            logger.info(f"Created collection: {collection_name} with {index_type} index")
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
        """Insert embeddings and their associated text with enhanced metadata support.

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
                metadata = [{"source": "unknown"} for _ in texts]
            
            # Prepare data with enhanced metadata extraction
            import json
            import time
            import random
            data = []
            
            # Generate a base ID for this batch (to avoid duplicates across batches)
            base_id = int(time.time() * 1000) % (2**31 - 1)  # Use 31-bit safe timestamp
            
            for idx, (emb, text, meta) in enumerate(zip(embeddings, texts, metadata)):
                # Extract common metadata fields for scalar filtering
                document_name = meta.get("document_name") or meta.get("filename", "")
                source = meta.get("source", "unknown")
                
                # Store metadata as JSON string for full preservation
                metadata_json = json.dumps(meta)
                
                # Generate unique ID: combine base timestamp with random number for uniqueness
                unique_id = base_id + idx + random.randint(1, 999)
                # Ensure it's a 31-bit positive integer for safety
                unique_id = abs(unique_id) % (2**31 - 1)
                if unique_id == 0:
                    unique_id = 1
                
                record = {
                    "id": unique_id,  # Use safe unique IDs
                    "vector": emb,  # Use 'vector' for MilvusClient API
                    "text": text,
                    "document_name": document_name,
                    "source": source,
                    "metadata": metadata_json,  # Full metadata as JSON
                }
                data.append(record)

            result = self.client.insert(
                collection_name=collection_name,
                data=data,
                db_name=self.db_name,
            )
            
            insert_count = result.get("insert_count", 0)
            if isinstance(insert_count, list):
                insert_count = len(insert_count)
            
            logger.info(f"Inserted {insert_count} embeddings into {collection_name}")
            logger.debug(f"  Insert result full: {result}")
            logger.debug(f"  Generated {len(data)} records with IDs: {[r['id'] for r in data]}")
            
            # Flush the collection to ensure data is written to disk
            try:
                self.client.flush(collection_name=collection_name, db_name=self.db_name)
                logger.debug(f"  Flushed collection {collection_name}")
            except Exception as flush_error:
                logger.warning(f"  Could not flush collection: {flush_error}")
            
            return result.get("insert_count", [])

        except Exception as e:
            logger.error(f"Failed to insert embeddings: {e}")
            raise

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        limit: int = 5,
        offset: int = 0,
        search_params: Optional[Dict[str, Any]] = None,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar embeddings with pagination and filtering.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            limit: Number of results to return
            offset: Number of results to skip (pagination)
            search_params: Optional search parameters (e.g., ef for HNSW)
            filter_expr: Optional filter expression for metadata filtering

        Returns:
            List of search results with text and scores
        """
        try:
            # Default search parameters optimized for HNSW
            if search_params is None:
                search_params = {"ef": 64}  # Trade-off between speed and accuracy
            
            results = self.client.search(
                collection_name=collection_name,
                data=[query_embedding],
                db_name=self.db_name,
                anns_field="vector",
                limit=limit + offset,  # Get extra results for offset
                search_params=search_params,
                output_fields=["text", "metadata", "document_name", "source"],
                filter=filter_expr,  # Apply filter if provided
            )

            # Process results with pagination
            processed_results = []
            for result_group in results:
                for idx, result in enumerate(result_group):
                    # Skip results before offset
                    if idx < offset:
                        continue
                    # Stop after limit
                    if len(processed_results) >= limit:
                        break
                    
                    entity = result.get("entity", {})
                    processed_results.append({
                        "text": entity.get("text", ""),
                        "metadata": entity.get("metadata", "{}"),
                        "document_name": entity.get("document_name", ""),
                        "source": entity.get("source", ""),
                        "distance": result.get("distance", 0),
                    })

            return processed_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    async def search_async(
        self,
        collection_name: str,
        query_embedding: List[float],
        limit: int = 5,
        offset: int = 0,
        search_params: Optional[Dict[str, Any]] = None,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Async search for similar embeddings with pagination and filtering.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            limit: Number of results to return
            offset: Number of results to skip
            search_params: Optional search parameters
            filter_expr: Optional filter expression

        Returns:
            List of search results
        """
        # Run search in thread pool executor to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(
                executor,
                self.search,
                collection_name,
                query_embedding,
                limit,
                offset,
                search_params,
                filter_expr
            )

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
    
    def search_by_source(
        self,
        collection_name: str,
        query_embedding: List[float],
        source: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for similar embeddings filtered by source.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            source: Source to filter by (e.g., 'milvus_docs')
            limit: Number of results to return

        Returns:
            List of search results filtered by source
        """
        filter_expr = f"source == '{source}'"
        return self.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            limit=limit,
            filter_expr=filter_expr,
        )
