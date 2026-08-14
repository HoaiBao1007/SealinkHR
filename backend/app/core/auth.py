import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.settings import settings


def get_password_hash(password: str) -> str:
    """Hash password using PBKDF2 with SHA-256 (100,000 iterations)."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    )
    return f"pbkdf2_sha256$100000${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify standard PBKDF2 password hash."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        key_hex = parts[3]

        test_key = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations
        )
        return hmac.compare_digest(test_key.hex(), key_hex)
    except Exception:
        return False


def generate_token(payload: dict, expires_in_seconds: int | None = None) -> str:
    """Generate custom HMAC-SHA256 signed token."""
    payload_copy = payload.copy()
    expires_in_seconds = expires_in_seconds or settings.token_expire_seconds
    payload_copy["exp"] = int(time.time()) + expires_in_seconds

    # Encode payload to base64
    payload_json = json.dumps(payload_copy).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")

    # Sign payload
    signature = hmac.new(
        settings.secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    return f"{payload_b64}.{signature_b64}"


def verify_token(token: str) -> dict | None:
    """Verify signature and expiration of a custom signed token."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature_b64 = parts

        # Verify signature
        expected_sig = hmac.new(
        settings.secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")

        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            return None

        # Decode payload (add padding if necessary)
        padded_b64 = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded_b64.encode("utf-8"))
        payload = json.loads(payload_json)

        # Check expiration
        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None
