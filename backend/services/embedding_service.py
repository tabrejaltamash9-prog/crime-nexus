"""
Embedding Service — Single source of truth for the BAAI/bge-large-en-v1.5 model.

Uses FastEmbed (ONNX runtime) for efficient CPU-based inference.
Singleton pattern ensures the model is loaded once and reused across all requests.
Both document chunk embeddings and query embeddings use the SAME model (dimension 1024).
"""

import asyncio
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
EMBEDDING_DIM = 1024

# ── Singleton Model Instance ─────────────────────────────────────────────────

_model = None
_model_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


def _get_sync_model():
    """Lazily load the FastEmbed model (synchronous, called from thread pool)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL} (dim={EMBEDDING_DIM})...")
        try:
            from fastembed import TextEmbedding
            _model = TextEmbedding(model_name=EMBEDDING_MODEL)
            logger.info(f"Embedding model loaded successfully: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load embedding model {EMBEDDING_MODEL}: {e}")
            raise
    return _model


def _embed_texts_sync(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts (synchronous, runs in thread pool)."""
    model = _get_sync_model()
    # fastembed returns a generator, convert to list
    embeddings = list(model.embed(texts))
    # Each embedding is a numpy array, convert to plain list of floats
    return [emb.tolist() for emb in embeddings]


def _embed_query_sync(query: str) -> List[float]:
    """Generate an embedding for a single query string (synchronous)."""
    model = _get_sync_model()
    # fastembed query embedding (uses query prefix for bge models)
    embeddings = list(model.query_embed(query))
    return embeddings[0].tolist()


# ── Async Public API ─────────────────────────────────────────────────────────

async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Async wrapper: generate embeddings for a batch of document texts.
    Runs the CPU-bound FastEmbed inference in a thread pool to avoid blocking
    the async event loop.
    
    Args:
        texts: List of text strings to embed.
        
    Returns:
        List of embedding vectors (each is a list of 1024 floats).
    """
    if not texts:
        return []
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _embed_texts_sync, texts)


async def embed_query(query: str) -> List[float]:
    """
    Async wrapper: generate an embedding for a single user query.
    Uses the BGE query-specific embedding (with instruction prefix).
    
    Args:
        query: The user's search query string.
        
    Returns:
        Embedding vector (list of 1024 floats).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _embed_query_sync, query)


def get_embedding_dimension() -> int:
    """Return the embedding dimension (1024 for bge-large-en-v1.5)."""
    return EMBEDDING_DIM
