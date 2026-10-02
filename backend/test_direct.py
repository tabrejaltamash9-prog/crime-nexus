import traceback
from PIL import Image
import logging

logging.basicConfig(level=logging.DEBUG)

try:
    from services.ocr.surya_engine import _load_models, _det_model, _det_processor, _rec_model, _rec_processor
    _load_models()
    from surya.ocr import run_ocr
    img = Image.open('test_ocr.jpg')
    res = run_ocr([img], [[None]], _det_model, _det_processor, _rec_model, _rec_processor)
    print(res)
except Exception as e:
    traceback.print_exc()
