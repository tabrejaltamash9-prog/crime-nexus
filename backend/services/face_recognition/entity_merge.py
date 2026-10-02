"""
Entity Merge Service — Multi-feature identity resolution scoring.

Combines face cosine similarity with name fuzzy matching, exact ID matching,
and case co-occurrence to produce a merge confidence score. Follows the
Splink-style probabilistic approach from the spec.

Critical constraint: NEVER auto-merge on face similarity alone.
"""

import logging
import os
from typing import Optional, Dict, Any, List

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────────

AUTO_MERGE_THRESHOLD = float(os.environ.get("ENTITY_MERGE_AUTO_THRESHOLD", "0.90"))
REVIEW_THRESHOLD = float(os.environ.get("ENTITY_MERGE_REVIEW_THRESHOLD", "0.65"))


# ── Feature Weights ──────────────────────────────────────────────────────────
# These weights sum to 1.0 and reflect relative importance per the spec.

WEIGHT_FACE = 0.40       # Face embedding cosine similarity
WEIGHT_NAME = 0.25       # Name string similarity (Jaro-Winkler)
WEIGHT_ID = 0.25         # Exact ID number match
WEIGHT_CASE_COOCCUR = 0.10  # Shared case co-occurrence


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_merge_candidates(
    face_cosine_sim: float,
    person_a: Dict[str, Any],
    person_b: Dict[str, Any],
    shared_case_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Compute a multi-feature merge confidence score between two Person candidates.
    
    Args:
        face_cosine_sim: Cosine similarity from Qdrant face search (0.0–1.0).
        person_a: First person's attributes (canonical_name, aliases, id_numbers, etc.)
        person_b: Second person's attributes.
        shared_case_ids: List of case_ids where both persons appear (if any).
        
    Returns:
        Dict with:
          - combined_score: Overall merge confidence
          - face_score: Weighted face component
          - name_score: Weighted name component
          - id_score: Weighted ID component
          - case_score: Weighted case co-occurrence component
          - features_matched: Count of non-face features with positive signal
          - can_auto_merge: Whether auto-merge is safe
    """
    # ── Face Similarity Score ──
    face_score = max(0.0, min(1.0, face_cosine_sim))
    
    # ── Name Similarity ──
    name_score = _compute_name_similarity(person_a, person_b)
    
    # ── Exact ID Match ──
    id_score = _compute_id_match(person_a, person_b)
    
    # ── Case Co-occurrence ──
    case_score = 1.0 if shared_case_ids and len(shared_case_ids) > 0 else 0.0
    
    # ── Combined Score ──
    combined = (
        WEIGHT_FACE * face_score +
        WEIGHT_NAME * name_score +
        WEIGHT_ID * id_score +
        WEIGHT_CASE_COOCCUR * case_score
    )
    
    # Count non-face features with positive signal
    features_matched = sum([
        name_score > 0.5,
        id_score > 0.5,
        case_score > 0.5,
    ])
    
    # ── Auto-merge gate ──
    # CRITICAL: Never auto-merge on face similarity alone
    can_auto_merge = combined >= AUTO_MERGE_THRESHOLD and features_matched >= 1
    
    result = {
        "combined_score": round(combined, 4),
        "face_score": round(face_score, 4),
        "name_score": round(name_score, 4),
        "id_score": round(id_score, 4),
        "case_score": round(case_score, 4),
        "features_matched": features_matched,
        "can_auto_merge": can_auto_merge,
    }
    
    logger.info(
        f"Merge score: combined={combined:.3f}, face={face_score:.3f}, "
        f"name={name_score:.3f}, id={id_score:.3f}, case={case_score:.3f}, "
        f"features_matched={features_matched}, auto_merge={can_auto_merge}"
    )
    
    return result


def decide_merge_action(score_result: Dict[str, Any]) -> str:
    """
    Decide what action to take based on the merge score.
    
    Returns:
        "auto_merge" | "review" | "reject"
    """
    combined = score_result["combined_score"]
    
    if score_result["can_auto_merge"]:
        return "auto_merge"
    elif combined >= REVIEW_THRESHOLD:
        return "review"
    else:
        return "reject"


# ── Private Helpers ──────────────────────────────────────────────────────────

def _compute_name_similarity(person_a: Dict, person_b: Dict) -> float:
    """
    Compute name similarity using fuzzy matching.
    
    Compares canonical_name and aliases using RapidFuzz partial ratio,
    taking the best match across all name combinations.
    """
    names_a = _collect_names(person_a)
    names_b = _collect_names(person_b)
    
    if not names_a or not names_b:
        return 0.0
    
    best_score = 0.0
    for na in names_a:
        for nb in names_b:
            # Use Jaro-Winkler for short names, partial ratio for longer ones
            if len(na) < 10 and len(nb) < 10:
                score = fuzz.WRatio(na.lower(), nb.lower()) / 100.0
            else:
                score = fuzz.partial_ratio(na.lower(), nb.lower()) / 100.0
            best_score = max(best_score, score)
    
    return best_score


def _compute_id_match(person_a: Dict, person_b: Dict) -> float:
    """
    Check for exact ID number matches (Aadhaar, PAN, passport, phone).
    
    Returns 1.0 if any ID matches exactly, 0.0 otherwise.
    Near-deterministic when present.
    """
    ids_a = set(person_a.get("id_numbers", []) + person_a.get("phone_numbers", []))
    ids_b = set(person_b.get("id_numbers", []) + person_b.get("phone_numbers", []))
    
    if not ids_a or not ids_b:
        return 0.0
    
    # Normalize: strip whitespace and convert to lowercase
    ids_a = {_normalize_id(i) for i in ids_a if i}
    ids_b = {_normalize_id(i) for i in ids_b if i}
    
    if ids_a.intersection(ids_b):
        return 1.0
    
    return 0.0


def _collect_names(person: Dict) -> List[str]:
    """Collect all name variants for a person (canonical name + aliases)."""
    names = []
    if person.get("canonical_name"):
        names.append(person["canonical_name"])
    names.extend(person.get("aliases", []))
    return [n for n in names if n and n.strip()]


def _normalize_id(id_str: str) -> str:
    """Normalize an ID number for comparison."""
    return id_str.strip().lower().replace(" ", "").replace("-", "")
