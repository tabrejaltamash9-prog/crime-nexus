import uuid
from datetime import datetime

cases_db = {}
evidence_db = {}

def create_case(title: str, investigators: list[str]) -> dict:
    case_id = str(uuid.uuid4())
    case = {
        "caseId": case_id,
        "title": title,
        "status": "open",
        "investigators": investigators
    }
    cases_db[case_id] = case
    return case

def get_case(case_id: str) -> dict:
    return cases_db.get(case_id)

def create_evidence(case_id: str, storage_path: str, mime_type: str, size: int, uploader: str, file_hash: str) -> dict:
    evidence_id = str(uuid.uuid4())
    evidence = {
        "evidenceId": evidence_id,
        "caseId": case_id,
        "storagePath": storage_path,
        "mimeType": mime_type,
        "size": size,
        "uploader": uploader,
        "timestamp": datetime.now(),
        "hash": file_hash,
        "status": "pending_ledger"
    }
    evidence_db[evidence_id] = evidence
    return evidence
