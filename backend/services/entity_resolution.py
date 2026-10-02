import re
import logging
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

AUTO_MERGE_THRESHOLD = 0.85

def normalize_mention(text: str) -> str:
    """Normalize case, punctuation, whitespace."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def calculate_similarity(ent_a: dict, ent_b: dict, context_a: list = None, context_b: list = None) -> float:
    """
    Calculate confidence score for entity resolution.
    Returns a float between 0.0 and 1.0.
    """
    if ent_a["type"] != ent_b["type"]:
        return 0.0

    # Strong identifiers
    if ent_a["type"] in ("PHONE", "VEHICLE", "ACCOUNT"):
        if normalize_mention(ent_a["text"]) == normalize_mention(ent_b["text"]):
            return 1.0
        return 0.0

    # Name similarity (fuzzy match)
    norm_a = normalize_mention(ent_a["text"])
    norm_b = normalize_mention(ent_b["text"])
    
    # Simple check for abbreviation e.g. "r kumar" vs "rahul kumar"
    # RapidFuzz partial ratio is good for this
    name_sim = fuzz.partial_ratio(norm_a, norm_b) / 100.0

    # Contextual similarity
    context_sim = 0.0
    if context_a and context_b:
        # If they share co-occurring entities
        shared_context = set(context_a).intersection(set(context_b))
        if shared_context:
            context_sim = 0.2  # Boost by 0.2 if they share context

    final_score = min(1.0, name_sim + context_sim)
    return final_score

def resolve_entities(extracted_entities: list, existing_graph_nodes: list):
    """
    Resolves extracted entities against existing nodes.
    Returns:
    - merges: list of (extracted_ent, existing_node_id)
    - new_entities: list of extracted_ent that should be created as new
    - review_queue: list of (extracted_ent, existing_node_id, confidence)
    """
    merges = []
    new_entities = []
    review_queue = []

    for ext_ent in extracted_entities:
        best_match = None
        best_score = 0.0

        for existing_node in existing_graph_nodes:
            score = calculate_similarity(ext_ent, existing_node)
            if score > best_score:
                best_score = score
                best_match = existing_node

        if best_match and best_score >= AUTO_MERGE_THRESHOLD:
            merges.append((ext_ent, best_match["id"]))
        elif best_match and best_score > 0.5:
            # Below auto-merge but similar enough to flag for review
            review_queue.append({
                "extracted": ext_ent,
                "existing_id": best_match["id"],
                "existing_name": best_match["text"],
                "confidence": best_score
            })
        else:
            new_entities.append(ext_ent)

    return {
        "merges": merges,
        "new_entities": new_entities,
        "review_queue": review_queue
    }
