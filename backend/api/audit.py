"""
Audit & Integrity Ledger API Routes.
Provides endpoints for retrieving the tamper-evident chain-of-custody
history and verifying ledger chain integrity.
"""

from fastapi import APIRouter, HTTPException

from models.schemas import (
    AuditChainResponse,
    AuditEntryResponse,
    ChainVerifyResponse,
)
from services.database import get_db
from services.ledger_service import get_chain, verify_chain, get_evidence_history

router = APIRouter(prefix="/audit", tags=["Audit & Ledger"])


@router.get("/case/{case_id}", response_model=AuditChainResponse)
async def get_case_audit_trail(case_id: str):
    """
    Retrieve the full chain-of-custody / audit trail for a case.
    Returns the ordered hash-chained ledger entries.
    """
    # Verify case exists
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT case_id FROM cases WHERE case_id = ?", (case_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
    finally:
        await db.close()

    chain = await get_chain(case_id)
    entries = [
        AuditEntryResponse(
            entryId=e["entryId"],
            caseId=e["caseId"],
            evidenceId=e["evidenceId"],
            sequence=e["sequence"],
            prevHash=e["prevHash"],
            evidenceHash=e["evidenceHash"],
            blockHash=e["blockHash"],
            action=e["action"],
            actor=e["actor"],
            details=e["details"],
            createdAt=e["createdAt"],
        )
        for e in chain
    ]
    return AuditChainResponse(entries=entries, total=len(entries))


@router.get("/case/{case_id}/verify", response_model=ChainVerifyResponse)
async def verify_case_chain(case_id: str):
    """
    Walk the full ledger chain for a case and verify every block hash.
    Returns whether the chain is intact or has been tampered with.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT case_id FROM cases WHERE case_id = ?", (case_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
    finally:
        await db.close()

    result = await verify_chain(case_id)
    return ChainVerifyResponse(
        valid=result["valid"],
        chainLength=result["length"],
        brokenAt=result["brokenAt"],
        message=result["message"],
    )


@router.get("/evidence/{evidence_id}")
async def get_evidence_audit_trail(evidence_id: str):
    """
    Retrieve all ledger entries for a specific evidence item.
    Shows the full custody history of a single piece of evidence.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT evidence_id FROM evidence WHERE evidence_id = ?",
            (evidence_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Evidence not found")
    finally:
        await db.close()

    history = await get_evidence_history(evidence_id)
    entries = [
        AuditEntryResponse(
            entryId=e["entryId"],
            caseId=e["caseId"],
            evidenceId=e["evidenceId"],
            sequence=e["sequence"],
            prevHash=e["prevHash"],
            evidenceHash=e["evidenceHash"],
            blockHash=e["blockHash"],
            action=e["action"],
            actor=e["actor"],
            details=e["details"],
            createdAt=e["createdAt"],
        )
        for e in history
    ]
    return AuditChainResponse(entries=entries, total=len(entries))
