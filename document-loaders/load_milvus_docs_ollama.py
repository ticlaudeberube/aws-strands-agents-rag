# Load all markdown files and embed them into Milvus
import json
import hashlib
import subprocess
import sys
from glob import glob
from tqdm import tqdm
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.tools import MilvusVectorDB, OllamaClient

settings = Settings()
collection_name = settings.ollama_collection_name
db_name = settings.loader_milvus_db_name

# Initialize clients - will be created in main function
vector_db = None
ollama_client = None

def ensure_milvus_docs():
    """Check if milvus_docs exist, download if needed"""
    docs_path = Path("./document-loaders/milvus_docs")
    
    # Check if directory is empty or doesn't exist
    if not docs_path.exists() or not any(docs_path.glob("**/*.md")):
        print("Milvus documentation not found. Downloading...")
        try:
            subprocess.run([
                "python", 
                "./document-loaders/download_milvus_docs.py"
            ], check=True)
            print("Documentation downloaded successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to download documentation: {e}")
            raise


def verify_ollama_setup():
    """Verify Ollama is running and required models are available."""
    print("\n📋 Verifying Ollama setup...")
    
    if not ollama_client.is_available():
        print(f"❌ Error: Cannot connect to Ollama at {settings.ollama_host}")
        print("   Make sure Ollama is running:")
        print("   - Run: ollama serve")
        print("   - Or on macOS: Open the Ollama app from Applications")
        raise RuntimeError("Ollama server is not available")
    
    print(f"✓ Ollama is running at {settings.ollama_host}")
    
    # Check available models
    available_models = ollama_client.get_available_models()
    if not available_models:
        print("⚠️  Warning: Could not retrieve model list from Ollama")
    else:
        print(f"✓ Available models: {len(available_models)} found")
        
        # Check for embedding model
        if settings.ollama_embed_model not in available_models:
            print(f"\n❌ Error: Embedding model '{settings.ollama_embed_model}' not found")
            print(f"   Available models: {', '.join(available_models)}")
            print(f"   Pull the model with: ollama pull {settings.ollama_embed_model}")
            raise RuntimeError(f"Required model '{settings.ollama_embed_model}' not found")
        
        print(f"✓ Embedding model '{settings.ollama_embed_model}' is available")
        
        # Check for generation model
        if settings.ollama_model not in available_models:
            print(f"\n⚠️  Warning: Generation model '{settings.ollama_model}' not found")
            print(f"   You can pull it with: ollama pull {settings.ollama_model}")
    
    print("✓ Ollama setup verified!\n")

def check_collection_and_confirm():
    """Check if collection exists and get user confirmation"""
    try:
        if vector_db is None:
            print("❌ Milvus client not initialized")
            return False
            
        collections = vector_db.client.list_collections(db_name=db_name)
        if collection_name in collections:
            print(f"Collection '{collection_name}' already exists.")
            choice = input("Do you want to (d)rop and recreate, or (a)bort? [d/a]: ").lower().strip()
            
            if choice == 'a':
                print("Process aborted by user.")
                return False
            elif choice == 'd':
                print(f"Dropping collection '{collection_name}'...")
                vector_db.delete_collection(collection_name)
                return True
            else:
                print("Invalid choice. Aborting.")
                return False
    except Exception as e:
        print(f"⚠️  Warning: Could not check collection: {e}")
        print("   Proceeding to create new collection...")
    
    return True

def create_collection(embedding_dim=None):
    """Create a collection for storing embeddings"""
    if embedding_dim is None:
        embedding_dim = settings.embedding_dim
    
    try:
        vector_db.create_collection(
            collection_name=collection_name,
            embedding_dim=embedding_dim,
        )
        print(f"Collection '{collection_name}' created successfully.")
    except Exception as e:
        print(f"Error creating collection: {e}")
        raise


def process(insertCollection=True):
    """Process and load Milvus documentation into vector database"""
    global vector_db, ollama_client
    
    # Initialize Ollama client
    print("\n📋 Initializing Ollama client...")
    try:
        ollama_client = OllamaClient(host=settings.ollama_host)
    except Exception as e:
        print(f"❌ Failed to initialize Ollama client: {e}")
        sys.exit(1)
    
    # Initialize Milvus client
    print("📋 Initializing Milvus client...")
    try:
        vector_db = MilvusVectorDB(
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=db_name,
        )
    except RuntimeError as e:
        print(f"\n❌ Milvus Connection Failed!")
        print(f"   Error: {e}")
        print(f"\n   To fix this:")
        print(f"   1. Check if Milvus is running:")
        print(f"      cd ../milvus-standalone && docker-compose ps")
        print(f"   2. If not running, start it:")
        print(f"      cd ../milvus-standalone && docker-compose up -d")
        print(f"   3. Wait 30 seconds for Milvus to be ready")
        print(f"   4. Try again: python document-loaders/load_milvus_docs_ollama.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error connecting to Milvus: {e}")
        sys.exit(1)
    
    # Ensure milvus_docs are downloaded
    ensure_milvus_docs()
    
    # Verify Ollama setup before processing
    verify_ollama_setup()
    
    # Check collection and get user confirmation
    if not check_collection_and_confirm():
        return
    
    text_lines = []
    MAX_CHUNK_LENGTH = settings.max_chunk_length

    print("Reading documentation files...")
    for file_path in tqdm(glob("./document-loaders/milvus_docs/en/**/*.md", recursive=True), desc="Reading files"):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                file_text = file.read()
            text_lines += file_text.split("# ")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

    # Further split long chunks to avoid embedding model context length limits
    processed_lines = []
    for line in text_lines:
        if len(line.strip()) > MAX_CHUNK_LENGTH:
            # Split long chunks into smaller pieces
            words = line.split()
            current_chunk = []
            for word in words:
                current_chunk.append(word)
                if len(" ".join(current_chunk)) > MAX_CHUNK_LENGTH:
                    if len(current_chunk) > 1:
                        current_chunk.pop()
                    processed_lines.append(" ".join(current_chunk))
                    current_chunk = [word]
            if current_chunk:
                processed_lines.append(" ".join(current_chunk))
        else:
            processed_lines.append(line)
    
    # Filter out empty/short chunks
    processed_lines = [line for line in processed_lines if line.strip() and len(line.strip()) >= 10]
    
    print(f"Processing {len(processed_lines)} text chunks...")
    embeddings_list = []
    texts_list = []
    metadata_list = []
    
    for i, line in enumerate(tqdm(processed_lines, desc="Creating embeddings")):
        try:
            # Generate embedding using Ollama
            embedding = ollama_client.embed_text(
                line,
                model=settings.ollama_embed_model,
            )
            
            if embedding:
                embeddings_list.append(embedding)
                texts_list.append(line)
                metadata_list.append({"source": "milvus_docs", "index": i})
        
        except Exception as e:
            tqdm.write(f"Failed to embed text chunk {i}: {e}")
            continue
    
    if len(embeddings_list) == 0:
        print("No embeddings created. Exiting.")
        return
    
    print(f"Created {len(embeddings_list)} embeddings")
    
    # Save to JSON file
    Path("./data").mkdir(exist_ok=True)
    data_to_save = [
        {
            "id": idx,
            "vector": emb,
            "text": text,
            "metadata": meta
        }
        for idx, (emb, text, meta) in enumerate(zip(embeddings_list, texts_list, metadata_list))
    ]
    
    with open("./data/embeddings.json", "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data_to_save)} embeddings to ./data/embeddings.json")
        
    if insertCollection:
        embedding_dim = len(embeddings_list[0])
        create_collection(embedding_dim)
        
        # Insert data using vector database
        print(f"Inserting {len(embeddings_list)} embeddings into Milvus...")
        try:
            vector_db.insert_embeddings(
                collection_name=collection_name,
                embeddings=embeddings_list,
                texts=texts_list,
                metadata=metadata_list,
            )
            print(f"✅ Successfully inserted {len(embeddings_list)} embeddings into collection '{collection_name}'")
        except Exception as e:
            print(f"❌ Error inserting embeddings: {e}")
            raise

if __name__ == "__main__":
    process()