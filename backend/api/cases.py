"""
Case Management API Routes.
Provides endpoints for creating, reading, updating, and listing investigation cases.
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from models.schemas import CaseCreate, CaseUpdate, CaseResponse, CaseListResponse
from services.database import get_db

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(payload: CaseCreate):
    """Create a new investigation case."""
    case_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO cases (case_id, title, description, status, priority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_id, payload.title, payload.description, "open", payload.priority, now, now),
        )

        # Insert investigators
        for inv in payload.investigators:
            await db.execute(
                "INSERT INTO case_investigators (case_id, investigator) VALUES (?, ?)",
                (case_id, inv),
            )

        await db.commit()
    finally:
        await db.close()

    return CaseResponse(
        caseId=case_id,
        title=payload.title,
        description=payload.description,
        status="open",
        investigators=payload.investigators,
        priority=payload.priority,
        createdAt=now,
        updatedAt=now,
        evidenceCount=0,
    )


@router.get("", response_model=CaseListResponse)
async def list_cases():
    """List all investigation cases."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT case_id, title, description, status, priority, created_at, updated_at FROM cases ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()

        cases = []
        for row in rows:
            # Get investigators
            inv_cursor = await db.execute(
                "SELECT investigator FROM case_investigators WHERE case_id = ?",
                (row["case_id"],),
            )
            inv_rows = await inv_cursor.fetchall()
            investigators = [r["investigator"] for r in inv_rows]

            # Get evidence count
            ev_cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM evidence WHERE case_id = ?",
                (row["case_id"],),
            )
            ev_row = await ev_cursor.fetchone()
            evidence_count = ev_row["cnt"] if ev_row else 0

            cases.append(
                CaseResponse(
                    caseId=row["case_id"],
                    title=row["title"],
                    description=row["description"],
                    status=row["status"],
                    investigators=investigators,
                    priority=row["priority"],
                    createdAt=row["created_at"],
                    updatedAt=row["updated_at"],
                    evidenceCount=evidence_count,
                )
            )

        return CaseListResponse(cases=cases, total=len(cases))
    finally:
        await db.close()


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str):
    """Get a single case by ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT case_id, title, description, status, priority, created_at, updated_at FROM cases WHERE case_id = ?",
            (case_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        inv_cursor = await db.execute(
            "SELECT investigator FROM case_investigators WHERE case_id = ?",
            (case_id,),
        )
        inv_rows = await inv_cursor.fetchall()
        investigators = [r["investigator"] for r in inv_rows]

        ev_cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM evidence WHERE case_id = ?",
            (case_id,),
        )
        ev_row = await ev_cursor.fetchone()
        evidence_count = ev_row["cnt"] if ev_row else 0

        return CaseResponse(
            caseId=row["case_id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            investigators=investigators,
            priority=row["priority"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
            evidenceCount=evidence_count,
        )
    finally:
        await db.close()


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(case_id: str, payload: CaseUpdate):
    """Update an existing case."""
    db = await get_db()
    try:
        # Verify case exists
        cursor = await db.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

        now = datetime.now(timezone.utc).isoformat()
        updates = []
        values = []

        if payload.title is not None:
            updates.append("title = ?")
            values.append(payload.title)
        if payload.description is not None:
            updates.append("description = ?")
            values.append(payload.description)
        if payload.status is not None:
            updates.append("status = ?")
            values.append(payload.status)
        if payload.priority is not None:
            updates.append("priority = ?")
            values.append(payload.priority)

        if updates:
            updates.append("updated_at = ?")
            values.append(now)
            values.append(case_id)
            await db.execute(
                f"UPDATE cases SET {', '.join(updates)} WHERE case_id = ?",
                values,
            )

        # Update investigators if provided
        if payload.investigators is not None:
            await db.execute("DELETE FROM case_investigators WHERE case_id = ?", (case_id,))
            for inv in payload.investigators:
                await db.execute(
                    "INSERT INTO case_investigators (case_id, investigator) VALUES (?, ?)",
                    (case_id, inv),
                )

        await db.commit()
    finally:
        await db.close()

    # Return updated case
    return await get_case(case_id)


@router.delete("/{case_id}", status_code=204)
async def delete_case(case_id: str):
    """Delete a case and all associated evidence."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

        await db.execute("DELETE FROM case_investigators WHERE case_id = ?", (case_id,))
        await db.execute("DELETE FROM evidence WHERE case_id = ?", (case_id,))
        await db.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        await db.commit()
    finally:
        await db.close()
