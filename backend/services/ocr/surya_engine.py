import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Lazy load models to avoid loading them if OCR_ENGINE != surya
_det_model = None
_det_processor = None
_rec_model = None
_rec_processor = None

def _load_models():
    global _det_model, _det_processor, _rec_model, _rec_processor
    if _det_model is not None:
        return

    logger.info("Loading Surya OCR models...")
    try:
        from surya.model.detection.model import load_model as load_det_model, load_processor as load_det_processor
        from surya.model.recognition.model import load_model as load_rec_model
        from surya.model.recognition.processor import load_processor as load_rec_processor
        
        # Determine device
        device = os.environ.get("OCR_DEVICE", "cpu")
        if device.lower() == "cuda":
            import torch
            if not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU for Surya OCR.")
                device = "cpu"
                
        _det_model, _det_processor = load_det_model(), load_det_processor()
        _rec_model, _rec_processor = load_rec_model(), load_rec_processor()
        logger.info("Surya OCR models loaded successfully.")
    except ImportError as e:
        logger.error(f"Failed to import surya-ocr: {e}")
        raise

def extract_document_text(image_pages: list) -> List[List[Dict[str, Any]]]:
    """
    Returns a list of page results, each containing structured blocks
    with text, confidence, and bounding box.
    """
    _load_models()
    from surya.ocr import run_ocr
    
    # Run OCR (langs=[None] auto-detects language if supported or defaults to English)
    # The API for run_ocr: run_ocr(images, langs, det_model, det_processor, rec_model, rec_processor)
    try:
        results = run_ocr(
            image_pages, 
            [None] * len(image_pages),
            _det_model, 
            _det_processor, 
            _rec_model, 
            _rec_processor
        )
    except Exception as e:
        logger.error(f"Surya OCR run_ocr failed: {e}")
        return []

    structured_pages = []
    for page_idx, page_result in enumerate(results):
        blocks = []
        for line in page_result.text_lines:
            blocks.append({
                "text": line.text,
                "confidence": line.confidence,
                "bbox": line.bbox,
                "page": page_idx
            })
        structured_pages.append(blocks)
    return structured_pages
