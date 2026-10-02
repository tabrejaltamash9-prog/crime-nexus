"""
Face Embedding Service — ArcFace embedding extraction and normalization.

The InsightFace buffalo_l model pack bundles ArcFace, so the `.embedding`
attribute on detected faces is already the ArcFace output. This module
validates and L2-normalizes the embedding before storage/search.
"""

import logging
import numpy as np
from typing import List, Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512  # ArcFace output dimension


def normalize_embedding(embedding: np.ndarray) -> List[float]:
    """
    L2-normalize a face embedding vector.
    
    Required for cosine similarity in Qdrant to work correctly —
    cosine distance on L2-normalized vectors equals the dot-product distance.
    
    Args:
        embedding: Raw ArcFace embedding (512-dim numpy array).
        
    Returns:
        L2-normalized embedding as a Python list of floats.
        
    Raises:
        ValueError: If the embedding has wrong dimensions or is all zeros.
    """
    if embedding is None:
        raise ValueError("Embedding is None — face detection may have failed.")
    
    if embedding.shape[0] != EMBEDDING_DIM:
        raise ValueError(
            f"Expected {EMBEDDING_DIM}-dim embedding, got {embedding.shape[0]}-dim"
        )
    
    norm = np.linalg.norm(embedding)
    if norm < 1e-10:
        raise ValueError("Embedding is a zero vector — likely a detection failure.")
    
    normalized = (embedding / norm).astype(np.float32)
    return normalized.tolist()


def validate_embedding(embedding: Optional[np.ndarray]) -> bool:
    """
    Check if an embedding is valid for storage.
    
    Returns:
        True if the embedding is a valid 512-dim non-zero vector.
    """
    if embedding is None:
        return False
    if not isinstance(embedding, np.ndarray):
        return False
    if embedding.shape[0] != EMBEDDING_DIM:
        return False
    if np.linalg.norm(embedding) < 1e-10:
        return False
    return True


def cosine_similarity(embedding_a: List[float], embedding_b: List[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.
    
    For L2-normalized vectors, this is equivalent to the dot product.
    
    Returns:
        Cosine similarity score in range [-1, 1] (typically 0–1 for face embeddings).
    """
    a = np.array(embedding_a, dtype=np.float32)
    b = np.array(embedding_b, dtype=np.float32)
    
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    
    return float(dot / (norm_a * norm_b))
