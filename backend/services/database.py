"""
SQLite Database Service for Crime Nexus.
Manages cases, evidence, and secure cryptographic entities.
"""

import aiosqlite
import os
from pathlib import Path

DATABASE_DIR = Path(__file__).resolve().parent.parent / "data"
DATABASE_PATH = DATABASE_DIR / "crime_nexus.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    officer_id TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    phone TEXT,
    profile_picture_url TEXT,
    password_hash TEXT NOT NULL,
    signing_pin_verifier TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'investigator',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_name TEXT NOT NULL,
    signing_public_key TEXT NOT NULL,
    encryption_public_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS certificates (
    certificate_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    officer_id TEXT NOT NULL,
    x509_pem TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS otp_codes (
    email TEXT PRIMARY KEY,
    otp TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_investigators (
    case_id TEXT NOT NULL,
    investigator TEXT NOT NULL,
    PRIMARY KEY (case_id, investigator),
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    encrypted_storage_path TEXT,
    encryption_algorithm TEXT,
    iv TEXT,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    uploader TEXT NOT NULL DEFAULT 'system',
    uploaded_at TEXT NOT NULL,
    original_sha256 TEXT,
    sha256_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    extracted_text TEXT DEFAULT '',
    ocr_status TEXT NOT NULL DEFAULT 'pending',
    qdrant_status TEXT NOT NULL DEFAULT 'pending',
    neo4j_status TEXT NOT NULL DEFAULT 'pending',
    doc_version INTEGER NOT NULL DEFAULT 1,
    chunk_count INTEGER DEFAULT 0,
    last_indexed_at TEXT,
    index_error TEXT,
    source_type TEXT DEFAULT 'unknown',
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence_key_wrappers (
    wrapper_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    recipient_device_id TEXT NOT NULL,
    wrapped_dek TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    actor_user_id TEXT,
    actor_officer_id TEXT,
    action TEXT NOT NULL,
    device_id TEXT,
    previous_event_hash TEXT,
    current_event_hash TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_signatures (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    evidence_version INTEGER NOT NULL,
    original_sha256 TEXT NOT NULL,
    digital_signature TEXT NOT NULL,
    signature_algorithm TEXT NOT NULL DEFAULT 'RSA-PSS-SHA256',
    signer_user_id TEXT NOT NULL,
    signer_officer_id TEXT NOT NULL,
    signer_device_id TEXT NOT NULL,
    certificate_id TEXT NOT NULL,
    signed_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'valid',
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    prev_hash TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS person_records (
    person_record_id TEXT PRIMARY KEY,
    face_id TEXT,
    case_id TEXT NOT NULL,
    full_name TEXT,
    aliases TEXT,
    age_approx INTEGER,
    date_of_birth TEXT,
    gender TEXT,
    id_numbers TEXT,
    height TEXT,
    build TEXT,
    complexion TEXT,
    distinguishing_marks TEXT,
    role_in_case TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    description TEXT NOT NULL,
    pose TEXT DEFAULT 'frontal',
    photo_url TEXT,
    photo_hash TEXT,
    photo_quality_score REAL,
    uploaded_by TEXT,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_person_records_case ON person_records(case_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_records_hash_case ON person_records(photo_hash, case_id);

CREATE TABLE IF NOT EXISTS ai_query_log (
    query_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    query_type TEXT NOT NULL,           -- 'global_search' | 'local_chat'
    case_id TEXT,                       -- NULL for global, set for local
    query_text TEXT NOT NULL,
    provider_used TEXT,
    model_used TEXT,
    context_strategy TEXT,              -- 'full_document' | 'chunk_rag' | 'summarized'
    failover_occurred INTEGER DEFAULT 0,
    failover_from TEXT,
    documents_used INTEGER DEFAULT 0,
    chunks_retrieved INTEGER DEFAULT 0,
    response_length INTEGER DEFAULT 0,
    latency_ms INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_query_log_user ON ai_query_log(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_query_log_case ON ai_query_log(case_id);
"""

async def get_db() -> aiosqlite.Connection:
    """Get an async database connection."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DATABASE_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db

async def init_db():
    """Initialize the database schema."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    finally:
        await db.close()

async def reset_db_for_prototype():
    """Drops all tables and recreates them. For prototype use only."""
    db = await get_db()
    try:
        tables = [
            "evidence_signatures", "audit_events", "evidence_key_wrappers",
            "evidence", "case_investigators", "cases", "otp_codes",
            "certificates", "devices", "users", "ledger_entries", "person_records"
        ]
        for table in tables:
            await db.execute(f"DROP TABLE IF EXISTS {table}")
        await db.commit()
    finally:
        await db.close()
    await init_db()
