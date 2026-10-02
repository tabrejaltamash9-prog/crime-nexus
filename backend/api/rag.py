"""
RAG API Routes — Evidence indexing and investigation chat endpoints.

POST /api/evidence/index  — Explicit indexing of extracted text into Qdrant
POST /api/chat/query      — Evidence-grounded chat with Gemini
"""

import logging
from fastapi import APIRouter, HTTPException, Depends

from services.auth_utils import get_current_user

from models.schemas import (
    IndexEvidenceRequest,
    IndexEvidenceResponse,
    ChatQueryRequest,
    ChatQueryResponse,
    SourceDocument,
)
from services import ingest_service, rag_service
from services.security_service import check_prompt_injection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["RAG"])


@router.post("/evidence/index", response_model=IndexEvidenceResponse)
async def index_evidence(request: IndexEvidenceRequest):
    """
    Index evidence text into the Qdrant vector store.
    
    This endpoint is for explicit/external indexing. The normal workflow
    automatically indexes evidence after OCR completes in the background.
    Use this for:
      - External callers providing pre-extracted text
      - Testing the indexing pipeline directly
    """
    logger.info(
        f"Explicit index request: document_id={request.document_id}, "
        f"case_id={request.case_id}"
    )
    
    try:
        total_chunks = await ingest_service.process_and_index_evidence(
            document_id=request.document_id,
            case_id=request.case_id,
            file_name=request.file_name,
            file_url=request.file_url,
            extracted_text=request.extracted_text,
            evidence_type=request.evidence_type,
            doc_version=1,
        )
        
        return IndexEvidenceResponse(
            status="indexed",
            total_chunks=total_chunks,
            document_id=request.document_id,
        )
        
    except ValueError as e:
        logger.warning(f"Indexing rejected: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Indexing failed: {str(e)}"
        )


@router.post("/chat/query", response_model=ChatQueryResponse)
async def chat_query(request: ChatQueryRequest, current_user: dict = Depends(get_current_user)):
    """
    Query the evidence base using natural language.
    
    Embeds the query, retrieves relevant evidence chunks from Qdrant
    (filtered by case_id), and generates an evidence-grounded answer
    using Gemini.
    
    Returns the answer along with source citations and relevance scores.
    """
    is_safe, reason = check_prompt_injection(request.query)
    if not is_safe:
        raise HTTPException(status_code=400, detail=reason)
        
    logger.info(
        f"Chat query for case_id={request.case_id}: "
        f"'{request.query[:80]}...'"
    )
    
    try:
        # Convert chat_history from Pydantic models to dicts
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.chat_history
        ]
        
        result = await rag_service.query_evidence(
            query=request.query,
            case_id=request.case_id,
            chat_history=history,
        )
        
        # Build typed source documents
        sources = [
            SourceDocument(
                document_id=src["document_id"],
                file_name=src["file_name"],
                file_url=src["file_url"],
                chunk_text=src["chunk_text"],
                chunk_index=src["chunk_index"],
                score=src["score"],
            )
            for src in result.get("sources", [])
        ]
        
        return ChatQueryResponse(
            answer=result["answer"],
            sources=sources,
        )
        
    except RuntimeError as e:
        logger.error(f"RAG query failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in chat query: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat query failed: {str(e)}"
        )
