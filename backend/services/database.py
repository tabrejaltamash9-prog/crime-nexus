"""
PostgreSQL Database Service for Crime Nexus (Supabase).
"""

import os
import re
import asyncpg
import asyncio
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

SCHEMA_SQL = """
-- Schema definition adapted for Postgres
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
    query_type TEXT NOT NULL,
    case_id TEXT,
    query_text TEXT NOT NULL,
    provider_used TEXT,
    model_used TEXT,
    context_strategy TEXT,
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

class AsyncpgCursorWrapper:
    def __init__(self, conn, query, args):
        self.conn = conn
        self.query = query
        self.args = args
        self._results = None

    def _convert_query(self, query):
        parts = query.split('?')
        if len(parts) == 1:
            return query
        new_query = parts[0]
        for i, part in enumerate(parts[1:], 1):
            new_query += f"${i}{part}"
            
        new_query = new_query.replace("INSERT OR REPLACE INTO otp_codes", "INSERT INTO otp_codes")
        if "INSERT INTO otp_codes" in new_query and "ON CONFLICT" not in new_query:
            new_query += " ON CONFLICT (email) DO UPDATE SET otp = EXCLUDED.otp, expires_at = EXCLUDED.expires_at, attempts = EXCLUDED.attempts"
            
        return new_query

    async def _execute(self):
        q = self._convert_query(self.query)
        try:
            if q.strip().upper().startswith("SELECT") or "RETURNING" in q.upper():
                rows = await self.conn.fetch(q, *self.args)
                self._results = rows
            else:
                await self.conn.execute(q, *self.args)
                self._results = []
        except Exception as e:
            logger.error(f"SQL Error: {e} | Query: {q} | Args: {self.args}")
            raise

    async def fetchone(self):
        if self._results is None:
            await self._execute()
        return dict(self._results[0]) if self._results else None

    async def fetchall(self):
        if self._results is None:
            await self._execute()
        return [dict(r) for r in self._results]

class AsyncpgConnectionWrapper:
    def __init__(self, pool):
        self.pool = pool
        self.conn = None

    async def execute(self, query, args=()):
        cursor = AsyncpgCursorWrapper(self.conn, query, args)
        await cursor._execute()
        return cursor

    async def commit(self):
        pass

    async def close(self):
        if self.conn:
            await self.pool.release(self.conn)
            self.conn = None

    async def executescript(self, script):
        await self.conn.execute(script)

_pool = None

async def get_db():
    global _pool
    if not DATABASE_URL or not DATABASE_URL.strip().startswith("postgres"):
        logger.error(f"CRITICAL ERROR: DATABASE_URL is missing or invalid. Current value: '{DATABASE_URL}'")
        logger.error(f"Available Environment Variable Keys: {list(os.environ.keys())}")
        raise ValueError(
            "\n\n=======================================================\n"
            "CRASH: DATABASE_URL is missing!\n"
            "Render cannot find your database connection string.\n"
            "Please check your Render Environment Variables:\n"
            "1. Ensure the key is exactly DATABASE_URL (no spaces).\n"
            "2. Ensure you clicked 'Save Changes' at the bottom of the page.\n"
            "=======================================================\n"
        )
        
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    
    wrapper = AsyncpgConnectionWrapper(_pool)
    wrapper.conn = await _pool.acquire()
    return wrapper

async def init_db():
    if not DATABASE_URL:
        return
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
    finally:
        await db.close()

async def reset_db_for_prototype():
    if not DATABASE_URL:
        return
    db = await get_db()
    try:
        tables = [
            "evidence_signatures", "audit_events", "evidence_key_wrappers",
            "evidence", "case_investigators", "cases", "otp_codes",
            "certificates", "devices", "users", "ledger_entries", "person_records", "ai_query_log"
        ]
        for table in tables:
            await db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    finally:
        await db.close()
    await init_db()
