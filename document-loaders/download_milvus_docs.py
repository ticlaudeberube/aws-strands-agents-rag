#!/usr/bin/env python3
"""Download and extract Milvus documentation"""

import os
import sys
import urllib.request
import zipfile
from pathlib import Path

def download_milvus_docs():
    """Download and extract Milvus docs"""
    
    # URLs and paths
    docs_url = "https://github.com/milvus-io/milvus-docs/releases/download/v2.4.6-preview/milvus_docs_2.4.x_en.zip"
    zip_file = "milvus_docs_2.4.x_en.zip"
    extract_dir = "milvus_docs"
    
    # Create document-loaders directory if it doesn't exist
    docs_dir = Path("document-loaders")
    docs_dir.mkdir(exist_ok=True)
    
    zip_path = docs_dir / zip_file
    extract_path = docs_dir / extract_dir
    
    try:
        # Check if already downloaded
        if extract_path.exists():
            print(f"Milvus docs already exist at {extract_path}")
            return
            
        print(f"Downloading Milvus docs from {docs_url}...")
        urllib.request.urlretrieve(docs_url, zip_path)
        print(f"Downloaded {zip_file}")
        
        print(f"Extracting to {extract_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        print(f"Extracted to {extract_path}")
        
        # Clean up zip file
        zip_path.unlink()
        print(f"Cleaned up {zip_file}")
        
        print(f"Milvus docs ready at {extract_path}")
        
    except Exception as e:
        print(f"Error downloading docs: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_milvus_docs()