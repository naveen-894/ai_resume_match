# auth.py
import os
from datetime import datetime, timedelta, timezone

import bcrypt
from cryptography.fernet import Fernet
from dotenv import find_dotenv, load_dotenv
from jose import jwt

load_dotenv(find_dotenv())

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not set. Add it to .env (see README).")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))

# Passwords used to be stored Fernet-encrypted (reversible). They are now bcrypt-hashed.
# The old key is only needed to migrate accounts created before the switch: each one is
# re-hashed on its next successful login. Remove it once every user has been migrated.
_legacy_key = os.getenv("LEGACY_PASSWORD_CIPHER_KEY")
LEGACY_CIPHER = Fernet(_legacy_key) if _legacy_key else None


def hash_password(password: str) -> str:
    """Hashes the plain password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def is_legacy_password(stored: str) -> bool:
    """True for passwords still stored in the old Fernet-encrypted format."""
    return not stored.startswith("$2")


def verify_password(plain_password: str, stored: str) -> bool:
    """Checks a plain password against a bcrypt hash (or a legacy Fernet-encrypted password)."""
    try:
        if not is_legacy_password(stored):
            return bcrypt.checkpw(plain_password.encode(), stored.encode())
        if LEGACY_CIPHER is None:
            return False
        return plain_password == LEGACY_CIPHER.decrypt(stored.encode()).decode()
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    """Creates a JWT access token with expiration."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    encoded_jwt = jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
