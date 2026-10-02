"""
Search API Routes — Global cross-case search and local case chat endpoints.

POST /api/search/global         — Cross-case hybrid Graph-RAG
POST /api/cases/{case_id}/chat  — Local case-level evidence chat
GET  /api/llm/providers         — Available LLM provider info
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends

from models.schemas import (
    GlobalSearchRequest,
    GlobalSearchResponse,
    CrossCaseConnection,
    LocalChatRequest,
    LocalChatResponse,
    DocumentUsed,
    SourceDocument,
    LLMProviderInfo,
    LLMProvidersResponse,
)
from services.auth_utils import get_current_user
from services.case_auth_service import get_authorized_case_ids, require_case_access
from services.global_search_service import global_search
from services.local_search_service import local_case_chat
from services.llm.gateway import get_gateway
from services.llm.config import get_default_provider, is_failover_enabled
from services.security_service import check_prompt_injection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Search & Chat"])


@router.post("/search/global", response_model=GlobalSearchResponse)
async def search_global(
    request: GlobalSearchRequest,
    current_user: dict = Depends(get_current_user),
    authorized_case_ids: List[str] = Depends(get_authorized_case_ids),
):
    """
    Cross-case global search using hybrid Graph-RAG.

    Searches across all cases the authenticated user has access to.
    Combines Qdrant vector search + Neo4j entity graph search.
    The case_ids list is derived from the user's role and case assignments —
    never from the frontend.
    """
    is_safe, reason = check_prompt_injection(request.query)
    if not is_safe:
        raise HTTPException(status_code=400, detail=reason)
        
    logger.info(
        f"Global search by {current_user['username']}: "
        f"'{request.query[:80]}...' across {len(authorized_case_ids)} cases"
    )

    try:
        result = await global_search(
            query=request.query,
            authorized_case_ids=authorized_case_ids,
            user_id=current_user["user_id"],
            username=current_user["username"],
            provider=request.provider,
            top_k=request.top_k,
        )

        return GlobalSearchResponse(
            answer=result["answer"],
            sources=[
                SourceDocument(
                    document_id=src.get("document_id", ""),
                    file_name=src.get("file_name", ""),
                    file_url=src.get("file_url", ""),
                    chunk_text=src.get("chunk_text", ""),
                    chunk_index=src.get("chunk_index", 0),
                    score=src.get("score", 0.0),
                )
                for src in result.get("sources", [])
            ],
            cross_case_connections=[
                CrossCaseConnection(
                    entity=conn.get("entity", ""),
                    type=conn.get("type", ""),
                    cases=conn.get("cases", []),
                    occurrences=conn.get("occurrences", 0),
                )
                for conn in result.get("cross_case_connections", [])
            ],
            provider_used=result.get("provider_used", "unknown"),
            model_used=result.get("model_used", "unknown"),
            context_strategy=result.get("context_strategy", "chunk_rag"),
            failover_occurred=result.get("failover_occurred", False),
        )

    except RuntimeError as e:
        logger.error(f"Global search failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in global search: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Global search failed: {str(e)}",
        )


@router.post("/cases/{case_id}/chat", response_model=LocalChatResponse)
async def case_chat(
    case_id: str,
    request: LocalChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Case-level evidence chat with long-context reasoning.

    Searches within a single case's evidence, attempts full-document
    context when the model supports it, and falls back to chunk-based RAG.
    """
    is_safe, reason = check_prompt_injection(request.query)
    if not is_safe:
        raise HTTPException(status_code=400, detail=reason)
        
    # Verify case access
    await require_case_access(case_id, current_user)

    logger.info(
        f"Case chat by {current_user['username']} for case {case_id}: "
        f"'{request.query[:80]}...'"
    )

    try:
        # Convert chat history to dicts
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.chat_history
        ]

        result = await local_case_chat(
            query=request.query,
            case_id=case_id,
            user_id=current_user["user_id"],
            username=current_user["username"],
            chat_history=history,
            provider=request.provider,
            top_k=request.top_k,
        )

        return LocalChatResponse(
            answer=result["answer"],
            sources=[
                SourceDocument(
                    document_id=src.get("document_id", ""),
                    file_name=src.get("file_name", ""),
                    file_url=src.get("file_url", ""),
                    chunk_text=src.get("chunk_text", ""),
                    chunk_index=src.get("chunk_index", 0),
                    score=src.get("score", 0.0),
                )
                for src in result.get("sources", [])
            ],
            documents_used=[
                DocumentUsed(
                    document_id=doc.get("document_id", ""),
                    file_name=doc.get("file_name", ""),
                    relevance_score=doc.get("relevance_score", 0.0),
                    chunk_count=doc.get("chunk_count", 0),
                    full_text_used=doc.get("full_text_used", False),
                )
                for doc in result.get("documents_used", [])
            ],
            context_strategy=result.get("context_strategy", "chunk_rag"),
            provider_used=result.get("provider_used", "unknown"),
            model_used=result.get("model_used", "unknown"),
            failover_occurred=result.get("failover_occurred", False),
        )

    except RuntimeError as e:
        logger.error(f"Case chat failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in case chat: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Case chat failed: {str(e)}",
        )


@router.get("/llm/providers", response_model=LLMProvidersResponse)
async def list_llm_providers(
    current_user: dict = Depends(get_current_user),
):
    """
    List available LLM providers.

    Returns safe (no-secret) information about each configured provider,
    including availability status, model names, and context window sizes.
    """
    gateway = get_gateway()
    providers_info = gateway.get_providers_info()

    return LLMProvidersResponse(
        providers=[
            LLMProviderInfo(
                provider=info["provider"],
                model=info["model"],
                context_window=info["context_window"],
                available=info["available"],
            )
            for info in providers_info
        ],
        default_provider=get_default_provider(),
        failover_enabled=is_failover_enabled(),
    )
