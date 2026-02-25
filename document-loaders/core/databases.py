"""Database operations for Milvus."""

from typing import List
from pymilvus import MilvusException, utility, Collection
from .client import get_client
from .exceptions import DatabaseError

def create_database(db_name: str | None) -> None:
    """Create or recreate a database."""
    if not db_name:
        raise DatabaseError("db_name is required")
    
    try:
        client = get_client()
        existing_databases = client.list_databases()
        
        if db_name in existing_databases:
            # Use the database context
            client.using_database(db_name)
            
            # Drop all collections in the database
            collections = utility.list_collections()
            for collection_name in collections:
                collection = Collection(name=collection_name)
                collection.drop()
                print(f"Collection '{collection_name}' has been dropped.")
            
            client.drop_database(db_name)
            print(f"Database '{db_name}' has been deleted.")
            
            # Create the database after dropping
            client.create_database(db_name)
            print(f"Database '{db_name}' created successfully.")
        else:
            # Database doesn't exist, create it
            client.create_database(db_name)
            print(f"Database '{db_name}' created successfully.")
        
    except MilvusException as e:
        raise DatabaseError(f"Failed to create database '{db_name}': {e}")

def drop_database(db_name: str | None) -> None:
    """Drop a database."""
    if not db_name:
        raise DatabaseError("db_name is required")
    
    try:
        client = get_client()
        client.drop_database(db_name=db_name)
        print("Database dropped successfully")
    except MilvusException as e:
        raise DatabaseError(f"Failed to drop database '{db_name}': {e}")

def list_databases() -> List[str]:
    """List all databases."""
    try:
        client = get_client()
        return client.list_databases()
    except MilvusException as e:
        raise DatabaseError(f"Failed to list databases: {e}")