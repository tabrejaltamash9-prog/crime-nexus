import pytest
import sys
import os
import json
import base64
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from fastapi.testclient import TestClient
from main import app
from services.storage_service import compute_sha256
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
import hashlib

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def test_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    return private_key, pub_pem

@pytest.fixture
def auth_token(client, test_keys):
    private_key, pub_pem = test_keys
    import uuid
    import sqlite3

    unique_id = uuid.uuid4().hex[:8]
    email = f"test_{unique_id}@police.gov"
    username = f"testoff_{unique_id}"

    # 1. Send OTP
    client.post("/auth/send-otp", json={"email": email})
    
    # Extract OTP from DB (hack for testing)
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend/data/crime_nexus.db'))
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT otp FROM otp_codes WHERE email = ?", (email,))
    otp_row = cursor.fetchone()
    otp = otp_row[0] if otp_row else "123456"
    conn.close()

    # 2. Verify OTP
    client.post("/auth/verify-otp", json={"email": email, "otp": otp})
    
    # 3. Register Finalize
    register_data = {
        "name": f"Test Officer {unique_id}",
        "phone": "1234567890",
        "email": email,
        "otp": otp,
        "username": username,
        "password": "securepassword",
        "confirm_password": "securepassword",
        "signing_pin": "1234",
        "confirm_signing_pin": "1234",
        "device_name": f"Test Device {unique_id}",
        "signing_public_key": pub_pem,
        "encryption_public_key": pub_pem
    }
    res = client.post("/auth/register", json=register_data)
    assert res.status_code == 201
    
    # 4. Login user
    response = client.post(
        "/auth/login",
        data={"username": username, "password": "securepassword"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None

@pytest.fixture
def case_id(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.post(
        "/cases",
        json={"title": "Test Case", "description": "Testing sig", "status": "open", "priority": "high", "investigators": ["testofficer"]},
        headers=headers
    )
    return response.json()["caseId"]

def test_digital_signature_valid(client, auth_token, case_id, test_keys):
    assert auth_token is not None
    private_key, _ = test_keys
    
    file_content = b"Test evidence data"
    files = {"file": ("test.txt", file_content, "text/plain")}
    original_sha256 = compute_sha256(file_content)
    
    data = {
        "case_id": case_id,
        "original_filename": "test.txt",
        "original_mime_type": "text/plain",
        "original_sha256": original_sha256,
        "encryption_algorithm": "NONE",
        "iv": "none",
        "wrapped_deks": json.dumps([])
    }
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    upload_res = client.post("/evidence/upload", files=files, data=data, headers=headers)
    print(upload_res.text)
    assert upload_res.status_code == 201
    
    evidence_id = upload_res.json()["evidenceId"]
    
    # Fetch device and cert IDs
    me_res = client.get("/auth/me", headers=headers)
    me_data = me_res.json()
    device_id = me_data.get("deviceId", "unknown")
    cert_id = me_data.get("certificateId", "unknown")

    # Sign the hash (double hashed as a UTF-8 string, matching frontend behavior)
    digest = hashlib.sha256(original_sha256.encode('utf-8')).digest()
    signature = private_key.sign(
        digest,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        Prehashed(hashes.SHA256())
    )
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    sign_data = {
        "digital_signature": signature_b64,
        "signature_algorithm": "RSA-PSS-SHA256",
        "device_id": device_id,
        "certificate_id": cert_id
    }
    sign_res = client.post(f"/evidence/{evidence_id}/sign", json=sign_data, headers=headers)
    assert sign_res.status_code == 200
    
    verify_res = client.get(f"/evidence/{evidence_id}/verify", headers=headers)
    assert verify_res.status_code == 200
    
    res_data = verify_res.json()
    assert res_data["integrityValid"] is True
    assert res_data["signatureValid"] is True
    assert res_data["signature"]["signer_id"] is not None

def test_digital_signature_tampered_file(client, auth_token, case_id, test_keys):
    private_key, _ = test_keys
    file_content = b"Original data"
    files = {"file": ("tamper_test.txt", file_content, "text/plain")}
    original_sha256 = compute_sha256(file_content)
    
    data = {
        "case_id": case_id,
        "original_filename": "test.txt",
        "original_mime_type": "text/plain",
        "original_sha256": original_sha256,
        "encryption_algorithm": "NONE",
        "iv": "none",
        "wrapped_deks": json.dumps([])
    }
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    upload_res = client.post("/evidence/upload", files=files, data=data, headers=headers)
    print(upload_res.text)
    evidence_id = upload_res.json()["evidenceId"]
    storage_path = upload_res.json()["storagePath"]
    
    me_res = client.get("/auth/me", headers=headers)
    me_data = me_res.json()
    
    digest = hashlib.sha256(original_sha256.encode('utf-8')).digest()
    signature = private_key.sign(
        digest,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        Prehashed(hashes.SHA256())
    )
    sign_res = client.post(f"/evidence/{evidence_id}/sign", json={
        "digital_signature": base64.b64encode(signature).decode('utf-8'),
        "signature_algorithm": "RSA-PSS-SHA256",
        "device_id": me_data.get("deviceId", "unknown"),
        "certificate_id": me_data.get("certificateId", "unknown")
    }, headers=headers)
    
    import os
    from services.storage_service import STORAGE_DIR
    full_path = STORAGE_DIR.parent / storage_path
    with open(full_path, 'wb') as f:
        f.write(b"Tampered data")
        
    verify_res = client.get(f"/evidence/{evidence_id}/verify", headers=headers)
    assert verify_res.status_code == 200
    res_data = verify_res.json()
    assert res_data["integrityValid"] is False
    assert res_data["signatureValid"] is True
