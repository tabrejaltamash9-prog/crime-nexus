import logging
import asyncio
import re

logger = logging.getLogger(__name__)

USE_STUB = False
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        logger.warning("spacy model 'en_core_web_sm' not found. Falling back to stub NLP.")
        USE_STUB = True
except ImportError:
    logger.warning("spacy not installed. Falling back to stub NLP.")
    USE_STUB = True

def _extract_entities_stub(text: str):
    # Fallback mocked extraction for hackathon
    entities = []
    
    # Mock some basic regex extraction as a fallback
    phone_pattern = r'\b\d{3}[-.]?\d{4}\b'
    phones = re.findall(phone_pattern, text)
    for p in phones:
        entities.append({"type": "PHONE", "text": p, "confidence": 0.95})
        
    if "Rahul" in text or "R. Kumar" in text:
        entities.append({"type": "PERSON", "text": "Rahul Kumar", "confidence": 0.90})
        
    if "offshore" in text.lower():
        entities.append({"type": "FINANCIAL", "text": "Offshore Account", "confidence": 0.85})
        
    return {
        "entities": entities,
        "relations": [
            {"from": "Rahul Kumar", "to": phones[0] if phones else "555-0199", "type": "HAS_PHONE"}
        ]
    }

async def extract_entities_and_relations(text: str):
    # If text is JSON from Surya OCR, extract the plain text
    import json
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "blocks" in data:
            text = " ".join([b.get("text", "") for b in data.get("blocks", [])])
    except json.JSONDecodeError:
        pass

    if USE_STUB or not text.strip():
        return _extract_entities_stub(text)
        
    def _run_spacy(t: str):
        doc = nlp(t)
        entities = []
        for ent in doc.ents:
            # Map spacy labels to our types
            ent_type = ent.label_
            if ent_type == "PERSON":
                mapped_type = "PERSON"
            elif ent_type in ("GPE", "LOC", "FAC"):
                mapped_type = "LOCATION"
            elif ent_type == "ORG":
                mapped_type = "ORGANIZATION"
            elif ent_type == "DATE" or ent_type == "TIME":
                mapped_type = "DATE_TIME"
            elif ent_type == "MONEY":
                mapped_type = "FINANCIAL"
            else:
                mapped_type = "OTHER"
                
            entities.append({
                "type": mapped_type,
                "text": ent.text,
                "confidence": 0.8  # spacy default ents don't have built-in conf score, mock it
            })
            
        # Regex for strong identifiers
        phone_pattern = r'\b\d{3}[-.]?\d{4}\b'
        for p in re.findall(phone_pattern, t):
            entities.append({"type": "PHONE", "text": p, "confidence": 0.95})
            
        return {"entities": entities, "relations": []}
        
    return await asyncio.to_thread(_run_spacy, text)
