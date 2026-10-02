import uuid
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization

from pathlib import Path

# Server root key for signing prototype certificates (persisted to survive server restarts)
CA_KEY_PATH = Path(__file__).parent.parent / "data" / "ca_root_key.pem"

def _get_or_create_root_key():
    if CA_KEY_PATH.exists():
        try:
            return serialization.load_pem_private_key(
                CA_KEY_PATH.read_bytes(),
                password=None
            )
        except Exception as e:
            print(f"Warning: Failed to load CA key from {CA_KEY_PATH}: {e}")

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )
    try:
        CA_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        CA_KEY_PATH.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
    except Exception as e:
        print(f"Warning: Could not save CA root key to {CA_KEY_PATH}: {e}")
    return key

_ROOT_KEY = _get_or_create_root_key()

_ROOT_SUBJECT = x509.Name([
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Crime Nexus Prototype CA"),
    x509.NameAttribute(NameOID.COMMON_NAME, u"Crime Nexus Internal Root"),
])

def issue_certificate(officer_id: str, public_key_pem: str) -> tuple[str, str]:
    """
    Issues a prototype X.509 certificate for the given officer and public key.
    Returns (x509_pem: str, fingerprint: str).
    """
    print(f"DEBUG: issue_certificate using _ROOT_KEY id={id(_ROOT_KEY)}")
    public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Crime Nexus Prototype"),
        x509.NameAttribute(NameOID.COMMON_NAME, officer_id),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, officer_id),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        _ROOT_SUBJECT
    ).public_key(
        public_key
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(timezone.utc)
    ).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=True,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ), critical=True
    ).sign(_ROOT_KEY, hashes.SHA256())
    
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    
    return cert_pem, fingerprint

def verify_certificate(cert_pem: str) -> bool:
    """Verifies the prototype certificate signature using the root key."""
    print(f"DEBUG: verify_certificate using _ROOT_KEY id={id(_ROOT_KEY)}")
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode('utf-8'))
        _ROOT_KEY.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
        
        now = datetime.now(timezone.utc)
        # In newer cryptography versions, not_valid_before/after might be timezone-aware or naive.
        # Handle naive datetime by adding utc timezone
        nb = cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before.replace(tzinfo=timezone.utc)
        na = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)
        
        if now < nb or now > na:
            print(f"DEBUG: Cert expired or not yet valid. now={now}, nb={nb}, na={na}")
            return False
            
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"DEBUG: Exception in verify_certificate: {e}")
        return False
