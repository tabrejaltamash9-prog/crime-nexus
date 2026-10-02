"""
Storage Service for Crime Nexus.
Handles file storage and SHA-256 hash computation.
Currently uses local filesystem; designed to be swappable with Supabase Storage.
"""

import hashlib
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone

from supabase import create_client, Client

STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "evidence_files"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Failed to initialize Supabase client: {e}")
        supabase = None

def ensure_storage_dir():
    """Ensure the evidence storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of binary data."""
    return hashlib.sha256(data).hexdigest()


async def store_file(
    case_id: str,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
) -> dict:
    """
    Store a file and return its metadata.
    Uploads to Supabase if configured, otherwise falls back to local storage.

    Returns:
        dict with keys: evidence_id, filename, storage_path, sha256_hash, size, mime_type
    """
    evidence_id = str(uuid.uuid4())
    ext = Path(original_filename).suffix
    stored_filename = f"{evidence_id}{ext}"
    
    sha256_hash = compute_sha256(file_bytes)
    
    # 1. Always save to local storage for processing (OCR/NLP)
    ensure_storage_dir()
    case_dir = STORAGE_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    file_path = case_dir / stored_filename
    file_path.write_bytes(file_bytes)
    
    local_storage_path = str(file_path.relative_to(STORAGE_DIR.parent))
    storage_path = local_storage_path
    
    if supabase:
        # 2. Upload to Supabase if configured
        supabase_path = f"{case_id}/{stored_filename}"
        try:
            res = supabase.storage.from_("evidence").upload(
                file=file_bytes,
                path=supabase_path,
                file_options={"content-type": mime_type}
            )
            # We can still keep the local_storage_path for the DB so that
            # local processing works without downloading.
            # If we wanted to point DB strictly to supabase, we'd do:
            # storage_path = supabase_path
        except Exception as e:
            print(f"Supabase upload failed: {e}. Kept local storage.")

    return {
        "evidence_id": evidence_id,
        "filename": stored_filename,
        "original_filename": original_filename,
        "storage_path": storage_path,
        "sha256_hash": sha256_hash,
        "size": len(file_bytes),
        "mime_type": mime_type,
    }

async def store_avatar(
    user_id: str,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
) -> str:
    """
    Store an avatar and return its public URL or path.
    Uploads to Supabase 'avatar' bucket if configured, otherwise local storage.
    """
    ext = Path(original_filename).suffix
    stored_filename = f"{user_id}{ext}"
    
    # Local fallback
    avatar_dir = STORAGE_DIR.parent / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    file_path = avatar_dir / stored_filename
    file_path.write_bytes(file_bytes)
    
    avatar_url = f"/avatars/{stored_filename}"
    
    if supabase:
        try:
            # Upload to 'avatar' bucket
            supabase_path = stored_filename
            supabase.storage.from_("avatar").upload(
                file=file_bytes,
                path=supabase_path,
                file_options={"content-type": mime_type, "upsert": "true"}
            )
            # Get public URL
            public_url = supabase.storage.from_("avatar").get_public_url(supabase_path)
            avatar_url = public_url
        except Exception as e:
            print(f"Supabase avatar upload failed: {e}. Kept local storage.")
            
    return avatar_url
