"""
Neo4j Person Node Management — Person identity graph for face recognition.

Extends the existing Neo4j service pattern with stub fallback.
Manages :Person nodes, APPEARS_IN edges, and SAME_AS candidate links.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ── In-Memory Stub ───────────────────────────────────────────────────────────
# Mirrors the pattern from neo4j_service.py for when Neo4j is unavailable.

_stub_persons: List[Dict] = []
_stub_appears_in: List[Dict] = []
_stub_same_as: List[Dict] = []
_stub_reviews: List[Dict] = []


def _get_neo4j_driver():
    """Get the Neo4j driver from the main service, or None if in stub mode."""
    try:
        from services.neo4j_service import driver, USE_STUB
        if USE_STUB or driver is None:
            return None
        return driver
    except Exception:
        return None


# ── Person Node Operations ───────────────────────────────────────────────────

def create_person_node(
    person_id: str,
    face_ids: List[str],
    resolution_status: str = "face_only",
    canonical_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a :Person node in Neo4j (or stub).
    
    Args:
        person_id: UUID for the person.
        face_ids: List of face_id UUIDs pointing to Qdrant.
        resolution_status: "face_only" | "name_only" | "merged" | "confirmed"
        canonical_name: Resolved name if available.
        
    Returns:
        The created person node as a dict.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    person = {
        "person_id": person_id,
        "canonical_name": canonical_name,
        "aliases": [],
        "id_numbers": [],
        "phone_numbers": [],
        "face_ids": face_ids,
        "resolution_status": resolution_status,
        "confidence_score": 0.0,
        "created_at": now,
        "last_updated": now,
    }
    
    driver = _get_neo4j_driver()
    
    if driver is None:
        _stub_persons.append(person)
        logger.info(f"[STUB] Created Person node: {person_id}")
        return person
    
    query = """
    CREATE (p:Person {
        person_id: $person_id,
        canonical_name: $canonical_name,
        aliases: $aliases,
        id_numbers: $id_numbers,
        phone_numbers: $phone_numbers,
        face_ids: $face_ids,
        resolution_status: $resolution_status,
        confidence_score: $confidence_score,
        created_at: $created_at,
        last_updated: $last_updated
    })
    RETURN p.person_id AS person_id
    """
    
    with driver.session() as session:
        session.run(query, **person)
    
    logger.info(f"Created Person node: {person_id}")
    return person


def add_appears_in(
    person_id: str,
    case_id: str,
    role: str,
    evidence_id: str,
    confidence: float,
) -> Dict[str, Any]:
    """Create an APPEARS_IN relationship between a Person and a Case."""
    edge = {
        "person_id": person_id,
        "case_id": case_id,
        "role": role,
        "evidence_id": evidence_id,
        "confidence": confidence,
    }
    
    driver = _get_neo4j_driver()
    
    if driver is None:
        _stub_appears_in.append(edge)
        logger.info(f"[STUB] Created APPEARS_IN: Person {person_id} → Case {case_id}")
        return edge
    
    query = """
    MATCH (p:Person {person_id: $person_id})
    MERGE (c:Case {case_id: $case_id})
    MERGE (p)-[r:APPEARS_IN {evidence_id: $evidence_id}]->(c)
    SET r.role = $role, r.confidence = $confidence
    """
    
    with driver.session() as session:
        session.run(query, **edge)
    
    logger.info(f"Created APPEARS_IN: Person {person_id} → Case {case_id}")
    return edge


def create_same_as(
    person_a_id: str,
    person_b_id: str,
    confidence: float,
    resolved_by: str,
) -> Dict[str, Any]:
    """Create a SAME_AS candidate link between two Person nodes for human review."""
    now = datetime.now(timezone.utc).isoformat()
    review_id = str(uuid.uuid4())
    
    link = {
        "review_id": review_id,
        "person_a_id": person_a_id,
        "person_b_id": person_b_id,
        "confidence": confidence,
        "resolved_by": resolved_by,
        "resolved_at": now,
        "status": "pending",
    }
    
    driver = _get_neo4j_driver()
    
    if driver is None:
        _stub_same_as.append(link)
        _stub_reviews.append(link)
        logger.info(f"[STUB] Created SAME_AS: {person_a_id} ↔ {person_b_id} (conf={confidence:.2f})")
        return link
    
    query = """
    MATCH (a:Person {person_id: $person_a_id}), (b:Person {person_id: $person_b_id})
    CREATE (a)-[r:SAME_AS {
        review_id: $review_id,
        confidence: $confidence,
        resolved_by: $resolved_by,
        resolved_at: $resolved_at,
        status: $status
    }]->(b)
    """
    
    with driver.session() as session:
        session.run(query, **link)
    
    _stub_reviews.append(link)  # Also track in memory for review queue
    logger.info(f"Created SAME_AS: {person_a_id} ↔ {person_b_id} (conf={confidence:.2f})")
    return link


def merge_persons(keep_id: str, merge_id: str) -> Dict[str, Any]:
    """
    Merge two Person nodes: keep `keep_id`, redirect all relationships from `merge_id`.
    
    This unions all properties (names, aliases, face_ids, etc.) and redirects
    all APPEARS_IN edges from the merged node to the kept node.
    """
    driver = _get_neo4j_driver()
    
    if driver is None:
        # Stub merge
        keep_node = next((p for p in _stub_persons if p["person_id"] == keep_id), None)
        merge_node = next((p for p in _stub_persons if p["person_id"] == merge_id), None)
        
        if keep_node and merge_node:
            # Union face_ids
            keep_node["face_ids"] = list(set(keep_node["face_ids"] + merge_node["face_ids"]))
            keep_node["aliases"] = list(set(keep_node.get("aliases", []) + merge_node.get("aliases", [])))
            keep_node["id_numbers"] = list(set(keep_node.get("id_numbers", []) + merge_node.get("id_numbers", [])))
            keep_node["phone_numbers"] = list(set(keep_node.get("phone_numbers", []) + merge_node.get("phone_numbers", [])))
            keep_node["resolution_status"] = "merged"
            keep_node["last_updated"] = datetime.now(timezone.utc).isoformat()
            
            if merge_node.get("canonical_name") and not keep_node.get("canonical_name"):
                keep_node["canonical_name"] = merge_node["canonical_name"]
            
            # Redirect APPEARS_IN edges
            for edge in _stub_appears_in:
                if edge["person_id"] == merge_id:
                    edge["person_id"] = keep_id
            
            _stub_persons.remove(merge_node)
        
        logger.info(f"[STUB] Merged Person {merge_id} into {keep_id}")
        return {"keep_id": keep_id, "merge_id": merge_id, "status": "merged"}
    
    # Real Neo4j merge
    query = """
    MATCH (keep:Person {person_id: $keep_id}), (merge:Person {person_id: $merge_id})
    SET keep.face_ids = keep.face_ids + merge.face_ids,
        keep.aliases = keep.aliases + merge.aliases,
        keep.id_numbers = keep.id_numbers + merge.id_numbers,
        keep.phone_numbers = keep.phone_numbers + merge.phone_numbers,
        keep.resolution_status = 'merged',
        keep.last_updated = $now
    WITH keep, merge
    OPTIONAL MATCH (merge)-[r:APPEARS_IN]->(c:Case)
    MERGE (keep)-[nr:APPEARS_IN]->(c)
    SET nr.role = r.role, nr.confidence = r.confidence, nr.evidence_id = r.evidence_id
    WITH merge
    DETACH DELETE merge
    """
    
    now = datetime.now(timezone.utc).isoformat()
    with driver.session() as session:
        session.run(query, keep_id=keep_id, merge_id=merge_id, now=now)
    
    logger.info(f"Merged Person {merge_id} into {keep_id}")
    return {"keep_id": keep_id, "merge_id": merge_id, "status": "merged"}


def get_person_with_cases(person_id: str) -> Optional[Dict[str, Any]]:
    """Get a Person node with all linked cases."""
    driver = _get_neo4j_driver()
    
    if driver is None:
        person = next((p for p in _stub_persons if p["person_id"] == person_id), None)
        if not person:
            return None
        
        linked_cases = [
            {"case_id": e["case_id"], "role": e["role"], "evidence_id": e["evidence_id"], "confidence": e["confidence"]}
            for e in _stub_appears_in if e["person_id"] == person_id
        ]
        
        return {**person, "linked_cases": linked_cases}
    
    query = """
    MATCH (p:Person {person_id: $person_id})
    OPTIONAL MATCH (p)-[r:APPEARS_IN]->(c:Case)
    RETURN p, collect({case_id: c.case_id, role: r.role, evidence_id: r.evidence_id, confidence: r.confidence}) AS cases
    """
    
    with driver.session() as session:
        result = session.run(query, person_id=person_id).single()
        if not result:
            return None
        
        person_data = dict(result["p"])
        person_data["linked_cases"] = [c for c in result["cases"] if c.get("case_id")]
        return person_data


def get_person_by_face_id(face_id: str) -> Optional[Dict[str, Any]]:
    """Find a Person node that contains a given face_id."""
    driver = _get_neo4j_driver()
    
    if driver is None:
        for person in _stub_persons:
            if face_id in person.get("face_ids", []):
                return person
        return None
    
    query = """
    MATCH (p:Person) WHERE $face_id IN p.face_ids
    RETURN p
    """
    
    with driver.session() as session:
        result = session.run(query, face_id=face_id).single()
        if result:
            return dict(result["p"])
    return None


def get_pending_reviews(case_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return SAME_AS candidate links pending human review."""
    pending = [r for r in _stub_reviews if r.get("status") == "pending"]
    
    if case_id:
        # Filter to reviews involving persons linked to this case
        linked_persons = {e["person_id"] for e in _stub_appears_in if e["case_id"] == case_id}
        pending = [
            r for r in pending
            if r["person_a_id"] in linked_persons or r["person_b_id"] in linked_persons
        ]
    
    return pending


def resolve_review(review_id: str, action: str, officer_id: str) -> Dict[str, Any]:
    """
    Resolve a pending SAME_AS review.
    
    Args:
        review_id: The review to resolve.
        action: "confirm_merge" or "reject"
        officer_id: Officer making the decision.
        
    Returns:
        Result dict with action taken.
    """
    review = next((r for r in _stub_reviews if r["review_id"] == review_id), None)
    if not review:
        return {"error": "Review not found"}
    
    review["status"] = action
    review["decided_by"] = officer_id
    review["decided_at"] = datetime.now(timezone.utc).isoformat()
    
    if action == "confirm_merge":
        merge_result = merge_persons(review["person_a_id"], review["person_b_id"])
        return {"action": "merged", **merge_result}
    else:
        return {"action": "rejected", "review_id": review_id}
