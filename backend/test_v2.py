import logging
import traceback
from PIL import Image

logging.basicConfig(level=logging.DEBUG)

try:
    from surya.recognition import RecognitionPredictor
    predictor = RecognitionPredictor()
    img = Image.open('test_ocr.jpg')
    # Run full page OCR
    results = predictor([img], full_page=True)
    print("RESULTS LENGTH:", len(results))
    print(results[0].model_dump_json(indent=2))
except Exception as e:
    traceback.print_exc()
