"""
Ingestion Service — The core indexing worker for the RAG pipeline.

Handles text normalization, semantic chunking, embedding generation,
and idempotent Qdrant upsert. This single function is called by both:
  1. The automatic background trigger (after OCR completes)
  2. The manual POST /evidence/{id}/index re-index endpoint

Idempotency:
  - Chunk IDs are deterministic: SHA256(document_id:doc_version:chunk_index)
  - Before upserting, all existing vectors for the document are deleted
  - Re-indexing increments doc_version, so stale chunks are never reused
"""

import asyncio
import hashlib
import logging
import re
import os
import json
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any

from qdrant_client.models import PointStruct

from services.embedding_service import embed_texts
from services import vector_store

logger = logging.getLogger(__name__)


# ── Text Normalization ───────────────────────────────────────────────────────

def is_json_ocr(raw: str) -> bool:
    if not raw.strip():
        return False
    try:
        data = json.loads(raw)
        return isinstance(data, dict) and "blocks" in data
    except json.JSONDecodeError:
        return False

def clean_ocr_text(raw: str) -> str:
    """
    Normalize raw OCR/extracted text for chunking and embedding.
    If it is JSON from Surya OCR, it just returns the JSON string untouched,
    so that downstream can parse it.
    """
    if not raw:
        return ""
        
    if is_json_ocr(raw):
        return raw # Don't strip JSON, parse it later
    
    # Remove NUL and control characters except newline, tab, carriage return
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    
    # Normalize unicode whitespace (non-breaking spaces, etc.)
    text = text.replace('\u00a0', ' ').replace('\u200b', '')
    
    # Collapse excessive newlines (3+ → 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Collapse excessive spaces (3+ → 1)
    text = re.sub(r' {3,}', ' ', text)
    
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()


# ── Semantic Chunking ────────────────────────────────────────────────────────

def chunk_by_layout(quality_gated_output: dict, max_chunk_tokens: int = 500) -> List[Dict[str, Any]]:
    chunks = []
    current_chunk_text = []
    current_chunk_conf = []
    current_tokens = 0

    try:
        threshold = float(os.environ.get("OCR_LOW_CONFIDENCE_THRESHOLD", "0.70"))
    except ValueError:
        threshold = 0.70

    for block in quality_gated_output.get("blocks", []):
        block_text = block.get("text", "")
        if not block_text:
            continue
            
        block_tokens = len(block_text.split())
        if current_tokens + block_tokens > max_chunk_tokens and current_chunk_text:
            chunks.append({
                "text": " ".join(current_chunk_text),
                "avg_confidence": sum(current_chunk_conf) / len(current_chunk_conf),
                "low_confidence": min(current_chunk_conf) < threshold
            })
            current_chunk_text, current_chunk_conf, current_tokens = [], [], 0

        current_chunk_text.append(block_text)
        current_chunk_conf.append(block.get("confidence", 1.0))
        current_tokens += block_tokens

    if current_chunk_text:
        chunks.append({
            "text": " ".join(current_chunk_text),
            "avg_confidence": sum(current_chunk_conf) / len(current_chunk_conf),
            "low_confidence": min(current_chunk_conf) < threshold
        })
    return chunks

def _chunk_text_sync(text: str) -> List[Dict[str, Any]]:
    """
    Split text into semantically meaningful chunks (synchronous).
    Returns a list of dicts with 'text', 'avg_confidence', and 'low_confidence'.
    """
    if is_json_ocr(text):
        try:
            data = json.loads(text)
            return chunk_by_layout(data)
        except Exception as e:
            logger.error(f"Failed to chunk JSON layout: {e}")
            # Fallback to normal chunking if JSON fails
            pass
            
    # For non-JSON text
    if len(text) < 50:
        return [{"text": text, "avg_confidence": 1.0, "low_confidence": False}] if text else []
    
    chunks_str = []
    if len(text) < 200:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        docs = splitter.create_documents([text])
        chunks_str = [doc.page_content for doc in docs]
    else:
        try:
            from langchain_experimental.text_splitter import SemanticChunker
            from langchain_huggingface import HuggingFaceEmbeddings
            
            embedding_model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
            embeddings = HuggingFaceEmbeddings(
                model_name=embedding_model,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            chunker = SemanticChunker(embeddings=embeddings, breakpoint_threshold_type="percentile")
            docs = chunker.create_documents([text])
            chunks_str = [doc.page_content for doc in docs]
            
            if not chunks_str:
                chunks_str = [text]
                
        except Exception as e:
            logger.warning(f"SemanticChunker failed ({e}), falling back to RecursiveCharacterTextSplitter")
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=800,
                chunk_overlap=100,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            docs = splitter.create_documents([text])
            chunks_str = [doc.page_content for doc in docs]
            
    return [{"text": c, "avg_confidence": 1.0, "low_confidence": False} for c in chunks_str]


# ── Deterministic Chunk ID ───────────────────────────────────────────────────

import uuid

def _make_chunk_id(document_id: str, doc_version: int, chunk_index: int) -> str:
    raw = f"{document_id}:{doc_version}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, raw))


# ── Main Indexing Pipeline ───────────────────────────────────────────────────

async def process_and_index_evidence(
    document_id: str,
    case_id: str,
    file_name: str,
    file_url: str,
    extracted_text: str,
    evidence_type: str,
    doc_version: int = 1,
) -> int:
    logger.info(
        f"Starting indexing pipeline for document={document_id}, "
        f"case={case_id}, version={doc_version}"
    )
    
    cleaned_text = clean_ocr_text(extracted_text)
    
    if not cleaned_text:
        logger.warning(f"Document {document_id}: empty text after cleaning, skipping indexing")
        raise ValueError(f"Document {document_id} has no indexable content after text cleaning")
    
    # ── Step 2: Semantic Chunking ──
    loop = asyncio.get_event_loop()
    structured_chunks = await loop.run_in_executor(None, _chunk_text_sync, cleaned_text)
    
    if not structured_chunks:
        logger.warning(f"Document {document_id}: chunking produced no results")
        raise ValueError(f"Document {document_id}: chunking produced no results")
    
    logger.info(f"Document {document_id}: split into {len(structured_chunks)} chunks")
    
    # Extract plain text for embeddings
    chunk_texts = [chunk["text"] for chunk in structured_chunks]
    
    # ── Step 3: Generate Embeddings ──
    logger.info(f"Document {document_id}: generating embeddings for {len(chunk_texts)} chunks...")
    embeddings = await embed_texts(chunk_texts)
    
    if len(embeddings) != len(chunk_texts):
        raise RuntimeError(
            f"Embedding count mismatch: {len(embeddings)} embeddings for {len(chunk_texts)} chunks"
        )
    
    # ── Step 4: Delete Existing Vectors (idempotency) ──
    try:
        await vector_store.delete_by_document(document_id)
    except Exception as e:
        logger.warning(f"Document {document_id}: delete_by_document failed (may be first index): {e}")
    
    # ── Step 5: Build Points & Upsert ──
    now = datetime.now(timezone.utc).isoformat()
    
    db = await vector_store.get_db() if hasattr(vector_store, 'get_db') else None # get sqlite to fetch source type
    source_type = "unknown"
    if db:
        try:
            cursor = await db.execute("SELECT source_type FROM evidence WHERE evidence_id = ?", (document_id,))
            row = await cursor.fetchone()
            if row and "source_type" in row.keys():
                source_type = row["source_type"]
        except Exception:
            pass
        finally:
            await db.close()
    else:
        # We can also rely on passing it, but let's default to unknown if not passed
        pass
    
    points = []
    for idx, (chunk, embedding) in enumerate(zip(structured_chunks, embeddings)):
        chunk_id = _make_chunk_id(document_id, doc_version, idx)
        
        point = PointStruct(
            id=chunk_id,
            vector=embedding,
            payload={
                "case_id": case_id,
                "document_id": document_id,
                "file_name": file_name,
                "file_url": file_url,
                "chunk_index": idx,
                "chunk_text": chunk["text"],
                "evidence_type": evidence_type,
                "doc_version": doc_version,
                "created_at": now,
                "ocr_confidence": chunk.get("avg_confidence", 1.0),
                "ocr_low_confidence_flag": chunk.get("low_confidence", False),
                "source_type": source_type,
            },
        )
        points.append(point)
    
    await vector_store.upsert_chunks(points)
    
    logger.info(
        f"Document {document_id}: indexing complete — "
        f"{len(points)} chunks indexed (version {doc_version})"
    )
    
    return len(points)
