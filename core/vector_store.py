"""ChromaDB embedded vector store initialization."""

import chromadb
from chromadb.api import ClientAPI
from pathlib import Path

from core.config import settings


def init_vector_store() -> ClientAPI:
    """Initialize ChromaDB in embedded persistent mode."""
    Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return client


def get_memory_collection(client: ClientAPI):
    """Get or create the memories collection."""
    return client.get_or_create_collection(
        name="resume_agent_memories",
        metadata={"hnsw:space": "cosine"},
    )


def get_resume_chunks_collection(client: ClientAPI):
    """Get or create the resume chunks collection for JD matching."""
    return client.get_or_create_collection(
        name="resume_chunks",
        metadata={"hnsw:space": "cosine"},
    )
