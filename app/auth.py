# auth.py
from jose import jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

SECRET_CIPHER_KEY = "QZt1u4rUZcJKmR8RY6YvFv2Pi3GVz0mYt6zvVx0M5uQ="
SECRET_KEY = "jDk2f9s0M4oP8XqZp7vBnA3yTq1eGr9cDkL0rRz8uTnNfVp1iLkOqRjTt3yHhGqBn"
ALGORITHM = "HS256"
CIPHER = Fernet(SECRET_CIPHER_KEY)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def encrypt_password(password: str) -> str:
    """Encrypts the plain password using Fernet symmetric encryption."""
    return CIPHER.encrypt(password.encode()).decode()


def decrypt_password(encrypted_password: str) -> str:
    """Decrypts the encrypted password."""
    return CIPHER.decrypt(encrypted_password.encode()).decode()


def verify_password(plain_password: str, encrypted_password: str) -> bool:
    """Compares plain text password with encrypted password."""
    try:
        return plain_password == decrypt_password(encrypted_password)
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    """Creates a JWT access token with expiration."""
    encoded_jwt = jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

