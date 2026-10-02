"""
Pydantic schemas for Crime Nexus API request/response models.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ── Auth Schemas ──────────────────────────────────────────────────────────────

class RegisterInit(BaseModel):
    name: str = Field(..., max_length=100)
    phone: str = Field(..., max_length=20)
    email: str = Field(..., max_length=100)
    role: str = Field("investigator", max_length=50)

class RegisterFinalize(BaseModel):
    name: str = Field(..., max_length=100)
    phone: str = Field(..., max_length=20)
    email: str = Field(..., max_length=100)
    otp: str = Field(..., min_length=6, max_length=6)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)
    device_name: str = Field(..., max_length=100)

class DeviceRegister(BaseModel):
    device_name: str = Field(..., max_length=100)

class DeviceResponse(BaseModel):
    device_id: str
    device_name: str
    status: str
    created_at: str

class UserResponse(BaseModel):
    user_id: str
    officer_id: str
    username: str
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    profile_picture_url: Optional[str] = None
    created_at: str
    status: str
    role: str

class Token(BaseModel):
    access_token: str
    token_type: str

class OTPRequest(BaseModel):
    email: str = Field(..., max_length=100)

class OTPVerify(BaseModel):
    email: str = Field(..., max_length=100)
    otp: str = Field(..., min_length=6, max_length=6)

class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)


# ── Case Schemas ──────────────────────────────────────────────────────────────


class CaseCreate(BaseModel):
    """Schema for creating a new case."""
    title: str = Field(..., min_length=1, max_length=200, description="Case title")
    description: str = Field("", max_length=2000, description="Case description")
    investigators: List[str] = Field(default_factory=list, description="List of investigator IDs")
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$", description="Case priority level")


class CaseUpdate(BaseModel):
    """Schema for updating an existing case."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(None, pattern="^(open|active|closed|archived)$")
    investigators: Optional[List[str]] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")


class CaseResponse(BaseModel):
    """Schema for case API responses."""
    caseId: str
    title: str
    description: str
    status: str
    investigators: List[str]
    priority: str
    createdAt: str
    updatedAt: str
    evidenceCount: int = 0


class CaseListResponse(BaseModel):
    """Schema for listing multiple cases."""
    cases: List[CaseResponse]
    total: int


# ── Evidence Schemas ──────────────────────────────────────────────────────────

class EvidenceResponse(BaseModel):
    """Schema for evidence API responses."""
    evidenceId: str
    caseId: str
    filename: str
    originalFilename: str
    storagePath: str
    mimeType: str
    size: int
    uploader: str
    uploadedAt: str
    originalSha256: str
    storageSha256: str
    status: str
    extractedText: Optional[str] = None
    ocrStatus: Optional[str] = None
    qdrantStatus: Optional[str] = None
    neo4jStatus: Optional[str] = None
    docVersion: Optional[int] = None
    chunkCount: Optional[int] = None
    lastIndexedAt: Optional[str] = None
    indexError: Optional[str] = None
    sourceType: Optional[str] = None


class EvidenceListResponse(BaseModel):
    """Schema for listing evidence for a case."""
    evidence: List[EvidenceResponse]
    total: int


class EvidenceVerifyResponse(BaseModel):
    evidenceId: str
    storedHash: str
    computedHash: str
    integrityValid: bool
    ledgerValid: Optional[bool] = None
    verifiedAt: str


# ── Audit / Ledger Schemas ────────────────────────────────────────────────

class AuditEntryResponse(BaseModel):
    """Schema for a single ledger chain entry."""
    entryId: str
    caseId: str
    evidenceId: str
    sequence: int
    prevHash: str
    evidenceHash: str
    blockHash: str
    action: str
    actor: str
    details: str
    createdAt: str


class AuditChainResponse(BaseModel):
    """Schema for the full audit chain."""
    entries: List[AuditEntryResponse]
    total: int


class ChainVerifyResponse(BaseModel):
    """Schema for chain verification result."""
    valid: bool
    chainLength: int
    brokenAt: Optional[int] = None
    message: str


# ── RAG / Investigation Chat Schemas ──────────────────────────────────────

class IndexEvidenceRequest(BaseModel):
    """Request body for explicit evidence indexing into the vector store."""
    case_id: str
    document_id: str
    file_name: str
    file_url: str
    extracted_text: str
    evidence_type: str = "Document"


class IndexEvidenceResponse(BaseModel):
    """Response after indexing evidence into the vector store."""
    status: str  # "indexed" | "error"
    total_chunks: int
    document_id: str


class ChatMessage(BaseModel):
    """A single message in the chat history."""
    role: str  # "user" | "assistant"
    content: str


class ChatQueryRequest(BaseModel):
    """Request body for the investigation chat query."""
    query: str = Field(..., min_length=1, max_length=2000)
    case_id: str
    chat_history: List[ChatMessage] = Field(default_factory=list)


class SourceDocument(BaseModel):
    """A source evidence chunk returned alongside the LLM answer."""
    document_id: str
    file_name: str
    file_url: str
    chunk_text: str
    chunk_index: int
    score: float


class ChatQueryResponse(BaseModel):
    """Response from the investigation chat query."""
    answer: str
    sources: List[SourceDocument]


class ReindexResponse(BaseModel):
    """Response after triggering a re-index for an evidence item."""
    status: str  # "accepted"
    evidence_id: str
    doc_version: int
    message: str


# ── Face Recognition Schemas ──────────────────────────────────────────────

class FaceDetectionResult(BaseModel):
    """A single detected face within an image."""
    face_id: str
    det_score: float
    quality_passed: bool
    rejection_reason: Optional[str] = None
    bbox: List[float]
    face_area_ratio: float = 0.0


class FaceMatch(BaseModel):
    """A matched identity result from face search."""
    person_id: Optional[str] = None
    confidence: float
    canonical_name: Optional[str] = None
    linked_cases: List[dict] = []
    evidence_refs: List[dict] = []


class PhotoUploadResponse(BaseModel):
    """Response from Mode A — evidence photo upload with face matching."""
    faces_detected: int
    faces: List[FaceDetectionResult]
    matches: List[FaceMatch]
    merge_actions: List[dict] = []


class FaceLookupResponse(BaseModel):
    """Response from Mode B — standalone face lookup."""
    query_face_quality: float
    results: List[FaceMatch]
    message: Optional[str] = None

class FaceSearchResult(BaseModel):
    case_id: str
    case_title: str
    case_status: str
    confidence: float
    person_record: Optional[dict] = None
    evidence_id: Optional[str] = None

class FaceSearchQueryResponse(BaseModel):
    query_face_quality: float
    results: List[FaceSearchResult]
    message: Optional[str] = None


class ReviewDecision(BaseModel):
    """Request body for resolving a SAME_AS review."""
    action: str = Field(..., pattern="^(confirm_merge|reject)$")
    officer_id: str


class ReviewQueueItem(BaseModel):
    """A pending SAME_AS candidate link for human review."""
    review_id: str
    person_a_id: str
    person_b_id: str
    confidence: float
    status: str
    created_at: Optional[str] = None


class ReviewQueueResponse(BaseModel):
    """Response listing pending reviews."""
    items: List[ReviewQueueItem]
    total: int


# ── Search & Chat Schemas (Multi-LLM Gateway) ──────────────────────────────

class GlobalSearchRequest(BaseModel):
    """Request body for cross-case global search."""
    query: str = Field(..., min_length=2, max_length=2000)
    filters: Optional[dict] = None
    provider: Optional[str] = None
    top_k: int = Field(15, ge=1, le=50)

class CrossCaseConnection(BaseModel):
    """An entity appearing in multiple cases."""
    entity: str
    type: str
    cases: List[str]
    occurrences: int

class GlobalSearchResponse(BaseModel):
    """Response from cross-case global search."""
    answer: str
    sources: List[SourceDocument]
    cross_case_connections: List[CrossCaseConnection] = []
    provider_used: str
    model_used: str
    context_strategy: str
    failover_occurred: bool = False

class LocalChatRequest(BaseModel):
    """Request body for case-level evidence chat."""
    query: str = Field(..., min_length=2, max_length=2000)
    chat_history: List[ChatMessage] = []
    provider: Optional[str] = None
    top_k: int = Field(10, ge=1, le=50)

class DocumentUsed(BaseModel):
    """Info about a document used in the context."""
    document_id: str
    file_name: str
    relevance_score: float
    chunk_count: int
    full_text_used: bool = False

class LocalChatResponse(BaseModel):
    """Response from case-level evidence chat."""
    answer: str
    sources: List[SourceDocument]
    documents_used: List[DocumentUsed] = []
    context_strategy: str  # "full_document" | "chunk_rag" | "summarized"
    provider_used: str
    model_used: str
    failover_occurred: bool = False

class LLMProviderInfo(BaseModel):
    """Safe (no secrets) info about an LLM provider."""
    provider: str
    model: str
    context_window: int
    available: bool

class LLMProvidersResponse(BaseModel):
    """Response listing all configured LLM providers."""
    providers: List[LLMProviderInfo]
    default_provider: str
    failover_enabled: bool
