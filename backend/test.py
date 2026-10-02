import asyncio
import logging
import traceback
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)
from services.ocr_service import _run_extraction

try:
    _run_extraction(Path('test_ocr.jpg'), 'image/jpeg')
except Exception as e:
    traceback.print_exc()
