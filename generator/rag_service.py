import os
import chromadb
from chromadb.config import Settings
import PyPDF2
from django.conf import settings
import google.generativeai as genai

# Specify an embedding model for Chroma (or use the default sentence-transformers)
# For simplicity in this demo, let's use the default ChromaDB sentence-transformers embedding
# It installs `sentence-transformers` automatically when queried, or we can use Google embeddings.

def get_chroma_client():
    db_path = os.path.join(settings.BASE_DIR, 'chroma_db')
    client = chromadb.PersistentClient(path=db_path)
    return client

def process_pdf_and_store(file_path, document_id, user_id=None):
    """
    Extracts text from a PDF, chunks it, and stores it in ChromaDB collection.
    """
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"

    # Simple chunking strategy
    chunk_size = 1000
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    
    client = get_chroma_client()
    collection = client.get_or_create_collection(name="genblog_documents")
    
    ids = []
    documents = []
    metadatas = []
    
    for i, chunk in enumerate(chunks):
        ids.append(f"doc_{document_id}_chunk_{i}")
        documents.append(chunk)
        metadatas.append({"document_id": document_id, "user_id": user_id or 0})
        
    # Add to Chroma
    if documents:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
    return True

def query_rag(query_text, user_id=None, top_k=3):
    """
    Queries ChromaDB for relevant chunks and returns them as a single string context.
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(name="genblog_documents")
    except Exception:
        # Collection might not exist yet
        return ""
        
    # Filter by user if applicable to ensure data privacy if wanted
    # For now, simple vector search
    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=top_k
        )
        
        context_chunks = []
        if results and 'documents' in results and len(results['documents']) > 0:
            for doc in results['documents'][0]:
                context_chunks.append(doc)
                
        return "\n---\n".join(context_chunks)
    except Exception as e:
        print(f"RAG query error: {e}")
        return ""
