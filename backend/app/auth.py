import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.facility import AdminUser


class AuthenticationConfigurationError(RuntimeError):
    """Raised when authentication cannot safely issue or validate tokens."""


def get_token_secret() -> str:
    secret = os.getenv("ADMIN_TOKEN_SECRET", "").strip()
    if not secret:
        raise AuthenticationConfigurationError(
            "ADMIN_TOKEN_SECRET is not configured. Set it in backend/.env and restart the backend."
        )
    return secret


def validate_auth_configuration() -> None:
    get_token_secret()


def normalize_username(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"pbkdf2_sha256$210000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, expected = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return scheme == "pbkdf2_sha256" and hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def issue_token(username: str) -> str:
    secret = get_token_secret()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": username, "exp": int(time.time()) + 8 * 3600}).encode()).decode().rstrip("=")
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def require_admin(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> AdminUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    try:
        payload, signature = authorization[7:].split(".", 1)
        secret = get_token_secret()
        if not secret or not hmac.compare_digest(signature, hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()):
            raise ValueError
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if decoded["exp"] < time.time():
            raise ValueError
        user = db.query(AdminUser).filter(AdminUser.username == decoded["sub"], AdminUser.active.is_(True)).first()
        if not user:
            raise ValueError
        return user
    except AuthenticationConfigurationError as error:
        raise HTTPException(status_code=503, detail="Authentication is not configured. Set ADMIN_TOKEN_SECRET and restart the backend.") from error
    except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")


def require_superadmin(admin: AdminUser = Depends(require_admin)) -> AdminUser:
    if (admin.role or "ADMIN").upper() != "SUPERADMIN":
        raise HTTPException(status_code=403, detail="Super administrator privileges required")
    return admin
