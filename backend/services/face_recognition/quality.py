"""
Face Quality Gating — Filters out low-quality face detections.

Reject or flag-for-review any detected face where:
  - det_score < FACE_DET_SCORE_MIN (default 0.65)
  - Bounding box area is under ~2% of image area
  - Face is heavily occluded (estimated via landmark visibility)

Low-quality embeddings poison the search index — this module ensures
they are never stored silently.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

FACE_DET_SCORE_MIN = float(os.environ.get("FACE_DET_SCORE_MIN", "0.65"))
MIN_FACE_AREA_RATIO = 0.02  # 2% of total image area
LANDMARK_MARGIN = 5  # pixels — how close to the edge a landmark can be before we flag it


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class QualityResult:
    """Result of quality assessment for a single face."""
    passed: bool
    det_score: float
    face_area_ratio: float
    landmarks_visible: bool
    rejection_reason: Optional[str] = None


# ── Public API ───────────────────────────────────────────────────────────────

def assess_quality(
    bbox: list,
    det_score: float,
    landmarks: Optional[np.ndarray],
    image_height: int,
    image_width: int,
) -> QualityResult:
    """
    Assess whether a detected face meets quality thresholds for embedding storage.
    
    Args:
        bbox: [x1, y1, x2, y2] bounding box coordinates.
        det_score: Detection confidence score from RetinaFace.
        landmarks: 5-point facial landmarks (numpy array), or None.
        image_height: Height of the source image in pixels.
        image_width: Width of the source image in pixels.
        
    Returns:
        QualityResult with pass/fail and reason.
    """
    image_area = image_height * image_width
    if image_area == 0:
        return QualityResult(
            passed=False,
            det_score=det_score,
            face_area_ratio=0.0,
            landmarks_visible=False,
            rejection_reason="Image has zero area",
        )
    
    # ── Check 1: Detection score ──
    if det_score < FACE_DET_SCORE_MIN:
        face_w = bbox[2] - bbox[0]
        face_h = bbox[3] - bbox[1]
        face_area = face_w * face_h
        face_area_ratio = face_area / image_area if image_area > 0 else 0.0
        
        return QualityResult(
            passed=False,
            det_score=det_score,
            face_area_ratio=face_area_ratio,
            landmarks_visible=_check_landmarks(landmarks, image_height, image_width),
            rejection_reason=f"Detection score {det_score:.2f} below threshold {FACE_DET_SCORE_MIN}",
        )
    
    # ── Check 2: Face area ratio ──
    face_w = bbox[2] - bbox[0]
    face_h = bbox[3] - bbox[1]
    face_area = face_w * face_h
    face_area_ratio = face_area / image_area
    
    if face_area_ratio < MIN_FACE_AREA_RATIO:
        return QualityResult(
            passed=False,
            det_score=det_score,
            face_area_ratio=face_area_ratio,
            landmarks_visible=_check_landmarks(landmarks, image_height, image_width),
            rejection_reason=f"Face too small: {face_area_ratio:.3f} of image area (min: {MIN_FACE_AREA_RATIO})",
        )
    
    # ── Check 3: Landmark visibility ──
    landmarks_visible = _check_landmarks(landmarks, image_height, image_width)
    if not landmarks_visible:
        return QualityResult(
            passed=False,
            det_score=det_score,
            face_area_ratio=face_area_ratio,
            landmarks_visible=False,
            rejection_reason="Facial landmarks partially outside image bounds (possible occlusion)",
        )
    
    # ── All checks passed ──
    return QualityResult(
        passed=True,
        det_score=det_score,
        face_area_ratio=face_area_ratio,
        landmarks_visible=True,
    )


def _check_landmarks(
    landmarks: Optional[np.ndarray],
    image_height: int,
    image_width: int,
) -> bool:
    """
    Check if all 5 facial landmarks are within image bounds.
    
    Returns True if landmarks are valid and within bounds, False otherwise.
    If landmarks are not available, returns True (benefit of the doubt).
    """
    if landmarks is None:
        return True  # No landmarks to check — don't reject
    
    try:
        for point in landmarks:
            x, y = float(point[0]), float(point[1])
            if (x < LANDMARK_MARGIN or x > image_width - LANDMARK_MARGIN or
                y < LANDMARK_MARGIN or y > image_height - LANDMARK_MARGIN):
                return False
        return True
    except (IndexError, TypeError):
        return True  # Malformed landmarks — don't reject on this alone
