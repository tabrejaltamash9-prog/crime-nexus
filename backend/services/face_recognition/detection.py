"""
Face Detection Service — RetinaFace wrapper via InsightFace.

Provides face detection with bounding boxes, landmarks, confidence scores,
and ArcFace embeddings. The model is lazy-loaded on first use to avoid
startup delay if the face recognition module is never invoked.
"""

import logging
import os
import numpy as np
import cv2
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

MODEL_PACK = os.environ.get("INSIGHTFACE_MODEL_PACK", "buffalo_l")
PROVIDER = os.environ.get("INSIGHTFACE_PROVIDER", "CPUExecutionProvider")
DET_SIZE = (640, 640)

# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class DetectedFace:
    """A single face detected in an image."""
    bbox: List[float]             # [x1, y1, x2, y2]
    det_score: float              # Detection confidence (0.0 – 1.0)
    landmarks: Optional[np.ndarray] = None  # 5-point facial landmarks
    embedding: Optional[np.ndarray] = None  # 512-dim ArcFace embedding (L2-normalized)
    face_index: int = 0           # Index within the image (for multi-face photos)


# ── Singleton Model ──────────────────────────────────────────────────────────

_face_app = None
_init_attempted = False


def _get_face_app():
    """Lazy-load the InsightFace model pack. Thread-safe via GIL."""
    global _face_app, _init_attempted
    
    if _face_app is not None:
        return _face_app
    
    if _init_attempted:
        # Already tried and failed — don't retry every call
        return None
    
    _init_attempted = True
    
    try:
        import insightface
        
        logger.info(f"Loading InsightFace model pack '{MODEL_PACK}' with provider '{PROVIDER}'...")
        
        app = insightface.app.FaceAnalysis(
            name=MODEL_PACK,
            providers=[PROVIDER, "CPUExecutionProvider"],  # fallback chain
        )
        app.prepare(ctx_id=0, det_size=DET_SIZE)
        
        _face_app = app
        logger.info("InsightFace model loaded successfully.")
        return _face_app
        
    except ImportError:
        logger.warning(
            "InsightFace is not installed. Face recognition features will be unavailable. "
            "Install with: pip install insightface onnxruntime opencv-python-headless"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to initialize InsightFace: {e}")
        return None


# ── Public API ───────────────────────────────────────────────────────────────

def detect_faces(image_bytes: bytes) -> List[DetectedFace]:
    """
    Detect all faces in an image.
    
    Args:
        image_bytes: Raw image file bytes (JPEG, PNG, etc.)
        
    Returns:
        List of DetectedFace objects with bounding boxes, scores, landmarks,
        and 512-dim ArcFace embeddings.
        
    Raises:
        RuntimeError: If InsightFace is not available.
        ValueError: If the image cannot be decoded.
    """
    app = _get_face_app()
    if app is None:
        raise RuntimeError(
            "Face detection is not available. InsightFace failed to initialize."
        )
    
    # Decode image from bytes
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Could not decode image. Ensure the file is a valid image format.")
    
    # Run detection — returns list of Face objects
    faces = app.get(img)
    
    results = []
    for idx, face in enumerate(faces):
        detected = DetectedFace(
            bbox=face.bbox.tolist(),
            det_score=float(face.det_score),
            landmarks=face.landmark if hasattr(face, 'landmark') else None,
            embedding=face.embedding if hasattr(face, 'embedding') else None,
            face_index=idx,
        )
        results.append(detected)
    
    logger.info(f"Detected {len(results)} face(s) in image ({img.shape[1]}x{img.shape[0]})")
    return results


def get_image_dimensions(image_bytes: bytes) -> tuple:
    """Get (height, width) of an image from bytes."""
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return (0, 0)
    return img.shape[:2]  # (height, width)
