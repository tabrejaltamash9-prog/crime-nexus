from fastapi import APIRouter, HTTPException
import logging
from typing import List, Dict, Any
from pydantic import BaseModel

import services.neo4j_service as neo4j_service
from services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["Graph"])

class NodeResponse(BaseModel):
    id: str
    text: str
    type: str
    confidence: float
    evidence_id: str = None
    case_id: str = None

class EdgeResponse(BaseModel):
    from_id: str
    to_id: str
    type: str
    confidence: float
    evidence_id: str = None

class GraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

@router.get("/case/{case_id}", response_model=GraphResponse)
async def get_case_graph(case_id: str):
    """Get the full entity/relationship graph for a case."""
    # Verify case exists
    db = await get_db()
    try:
        cursor = await db.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
    finally:
        await db.close()

    graph_data = neo4j_service.get_graph(case_id)
    return graph_data

@router.get("/entities/review-queue", response_model=List[Dict[str, Any]])
async def get_review_queue(case_id: str):
    """Get the entity resolution review queue for a case."""
    return neo4j_service.get_review_queue(case_id)
