import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_low_confidence_threshold() -> float:
    try:
        return float(os.environ.get("OCR_LOW_CONFIDENCE_THRESHOLD", "0.70"))
    except ValueError:
        return 0.70

def apply_quality_gate(structured_pages: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    threshold = get_low_confidence_threshold()
    flagged_blocks = []
    all_blocks = []
    
    for page in structured_pages:
        for block in page:
            all_blocks.append(block)
            if block.get("confidence", 1.0) < threshold:
                flagged_blocks.append(block)

    overall_doc_confidence = sum(b.get("confidence", 1.0) for b in all_blocks) / len(all_blocks) if all_blocks else 0.0

    return {
        "blocks": all_blocks,
        "flagged_blocks": flagged_blocks,
        "overall_confidence": overall_doc_confidence,
        "needs_review": len(flagged_blocks) > 0
    }
