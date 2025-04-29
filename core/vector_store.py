import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
from pathlib import Path
import faiss
from ..config.settings import settings

logger = logging.getLogger(__name__)

class VectorStore:
    """Store and retrieve document embeddings for semantic search"""
    
    def __init__(self, workspace_path: Optional[str] = None, embedding_model: str = "all-MiniLM-L6-v2"):
        self.workspace_path = workspace_path or settings.filesystem.workspace_path
        self.storage_path = os.path.join(self.workspace_path, ".vector_store")
        self.embedding_model_name = embedding_model
        self.embedding_model = None
        self.index = None
        self.documents = []
        
        # Create storage directory
        os.makedirs(self.storage_path, exist_ok=True)
        
        # Initialize
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize the vector store"""
        try:
            # Load embedding model
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            
            # Check if we have an existing index
            index_path = os.path.join(self.storage_path, "faiss_index.bin")
            documents_path = os.path.join(self.storage_path, "documents.json")
            
            if os.path.exists(index_path) and os.path.exists(documents_path):
                # Load existing index
                self.index = faiss.read_index(index_path)
                
                # Load documents
                with open(documents_path, 'r') as f:
                    self.documents = json.load(f)
                    
                logger.info(f"Loaded existing vector store with {len(self.documents)} documents")
            else:
                # Create new index
                embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
                self.index = faiss.IndexFlatL2(embedding_dim)
                self.documents = []
                logger.info(f"Created new vector store with dimension {embedding_dim}")
        
        except Exception as e:
            logger.error(f"Error initializing vector store: {e}")
            raise
    
    def add_document(self, text: str, metadata: Dict[str, Any] = None) -> int:
        """Add a document to the vector store
        
        Args:
            text: Document text
            metadata: Optional metadata for the document
            
        Returns:
            Document ID
        """
        try:
            # Get embedding
            embedding = self.embedding_model.encode([text])
            
            # Add to index
            self.index.add(embedding)
            
            # Add to documents
            doc_id = len(self.documents)
            self.documents.append({
                "id": doc_id,
                "text": text,
                "metadata": metadata or {}
            })
            
            # Save
            self._save()
            
            return doc_id
            
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            return -1
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> List[int]:
        """Add multiple documents to the vector store
        
        Args:
            documents: List of documents with 'text' and optional 'metadata'
            
        Returns:
            List of document IDs
        """
        try:
            # Get embeddings for all documents
            texts = [doc["text"] for doc in documents]
            embeddings = self.embedding_model.encode(texts)
            
            # Add to index
            self.index.add(embeddings)
            
            # Add to documents
            doc_ids = []
            for i, doc in enumerate(documents):
                doc_id = len(self.documents)
                self.documents.append({
                    "id": doc_id,
                    "text": doc["text"],
                    "metadata": doc.get("metadata", {})
                })
                doc_ids.append(doc_id)
            
            # Save
            self._save()
            
            return doc_ids
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return []
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for documents similar to the query
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of documents with similarity scores
        """
        try:
            # Get query embedding
            query_embedding = self.embedding_model.encode([query])
            
            # Search
            distances, indices = self.index.search(query_embedding, top_k)
            
            # Get results
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < len(self.documents) and idx >= 0:
                    doc = self.documents[idx]
                    results.append({
                        "id": doc["id"],
                        "text": doc["text"],
                        "metadata": doc["metadata"],
                        "score": float(1.0 - distances[0][i] / 2.0)  # Convert L2 distance to similarity score
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []
    
    def _save(self) -> None:
        """Save the vector store to disk"""
        try:
            # Save index
            index_path = os.path.join(self.storage_path, "faiss_index.bin")
            faiss.write_index(self.index, index_path)
            
            # Save documents
            documents_path = os.path.join(self.storage_path, "documents.json")
            with open(documents_path, 'w') as f:
                json.dump(self.documents, f)
                
        except Exception as e:
            logger.error(f"Error saving vector store: {e}")
            
    def clear(self) -> None:
        """Clear the vector store"""
        try:
            # Create new index
            embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            self.index = faiss.IndexFlatL2(embedding_dim)
            self.documents = []
            
            # Save
            self._save()
            
            logger.info("Vector store cleared")
            
        except Exception as e:
            logger.error(f"Error clearing vector store: {e}")