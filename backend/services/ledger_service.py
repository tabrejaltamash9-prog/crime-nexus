"""
Integrity Ledger Service for Crime Nexus.

Implements a hash-chained local log as a simplified stand-in for
Hyperledger Fabric.  Each ledger entry contains:

  - The SHA-256 hash of the evidence artifact
  - The hash of the *previous* ledger entry (genesis block uses a
    well-known constant)
  - A composite block hash  =  SHA-256( prev_hash | evidence_hash |
    timestamp | action | actor )

This guarantees that any retrospective tampering with an entry will
break every subsequent block hash, providing tamper-evidence.
"""

import hashlib
import uuid
from datetime import datetime, timezone

from services.database import get_db

# Well-known genesis sentinel — used as prev_hash for the very first
# entry in every case's ledger chain.
GENESIS_HASH = "0" * 64


def _compute_block_hash(
    prev_hash: str,
    evidence_hash: str,
    timestamp: str,
    action: str,
    actor: str,
) -> str:
    """Compute the composite block hash for a ledger entry."""
    payload = f"{prev_hash}|{evidence_hash}|{timestamp}|{action}|{actor}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _get_latest_block_hash(case_id: str) -> str:
    """Return the block_hash of the most recent ledger entry for a case,
    or GENESIS_HASH if the chain is empty."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT block_hash FROM ledger_entries WHERE case_id = ? ORDER BY sequence DESC LIMIT 1",
            (case_id,),
        )
        row = await cursor.fetchone()
        return row["block_hash"] if row else GENESIS_HASH
    finally:
        await db.close()


async def _get_next_sequence(case_id: str) -> int:
    """Return the next sequence number for a case's ledger chain."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_seq FROM ledger_entries WHERE case_id = ?",
            (case_id,),
        )
        row = await cursor.fetchone()
        return row["next_seq"]
    finally:
        await db.close()


async def record_event(
    case_id: str,
    evidence_id: str,
    evidence_hash: str,
    action: str,
    actor: str = "system",
    details: str = "",
) -> dict:
    """
    Append a new tamper-evident entry to the ledger chain.

    Actions: UPLOAD, VERIFY, ACCESS, DELETE, STATUS_CHANGE
    """
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    prev_hash = await _get_latest_block_hash(case_id)
    sequence = await _get_next_sequence(case_id)
    block_hash = _compute_block_hash(prev_hash, evidence_hash, now, action, actor)

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO ledger_entries
               (entry_id, case_id, evidence_id, sequence,
                prev_hash, evidence_hash, block_hash,
                action, actor, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id, case_id, evidence_id, sequence,
                prev_hash, evidence_hash, block_hash,
                action, actor, details, now,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "entryId": entry_id,
        "caseId": case_id,
        "evidenceId": evidence_id,
        "sequence": sequence,
        "prevHash": prev_hash,
        "evidenceHash": evidence_hash,
        "blockHash": block_hash,
        "action": action,
        "actor": actor,
        "details": details,
        "createdAt": now,
    }


async def get_chain(case_id: str) -> list[dict]:
    """Return the full ordered ledger chain for a case."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT entry_id, case_id, evidence_id, sequence,
                      prev_hash, evidence_hash, block_hash,
                      action, actor, details, created_at
               FROM ledger_entries
               WHERE case_id = ?
               ORDER BY sequence ASC""",
            (case_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "entryId": r["entry_id"],
                "caseId": r["case_id"],
                "evidenceId": r["evidence_id"],
                "sequence": r["sequence"],
                "prevHash": r["prev_hash"],
                "evidenceHash": r["evidence_hash"],
                "blockHash": r["block_hash"],
                "action": r["action"],
                "actor": r["actor"],
                "details": r["details"],
                "createdAt": r["created_at"],
            }
            for r in rows
        ]
    finally:
        await db.close()


async def verify_chain(case_id: str) -> dict:
    """
    Walk the full ledger chain for a case and verify every block hash.
    Returns overall validity and the first broken link (if any).
    """
    chain = await get_chain(case_id)
    if not chain:
        return {"valid": True, "length": 0, "brokenAt": None, "message": "Empty chain"}

    prev_hash = GENESIS_HASH
    for entry in chain:
        expected = _compute_block_hash(
            prev_hash,
            entry["evidenceHash"],
            entry["createdAt"],
            entry["action"],
            entry["actor"],
        )
        if expected != entry["blockHash"]:
            return {
                "valid": False,
                "length": len(chain),
                "brokenAt": entry["sequence"],
                "message": f"Chain integrity broken at block #{entry['sequence']} "
                           f"(entry {entry['entryId']}). "
                           f"Expected {expected[:16]}…, got {entry['blockHash'][:16]}…",
            }
        prev_hash = entry["blockHash"]

    return {
        "valid": True,
        "length": len(chain),
        "brokenAt": None,
        "message": f"All {len(chain)} blocks verified — chain intact",
    }


async def get_evidence_history(evidence_id: str) -> list[dict]:
    """Return all ledger entries for a specific evidence item."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT entry_id, case_id, evidence_id, sequence,
                      prev_hash, evidence_hash, block_hash,
                      action, actor, details, created_at
               FROM ledger_entries
               WHERE evidence_id = ?
               ORDER BY sequence ASC""",
            (evidence_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "entryId": r["entry_id"],
                "caseId": r["case_id"],
                "evidenceId": r["evidence_id"],
                "sequence": r["sequence"],
                "prevHash": r["prev_hash"],
                "evidenceHash": r["evidence_hash"],
                "blockHash": r["block_hash"],
                "action": r["action"],
                "actor": r["actor"],
                "details": r["details"],
                "createdAt": r["created_at"],
            }
            for r in rows
        ]
    finally:
        await db.close()
