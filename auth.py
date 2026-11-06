"""Authentication utilities with bcrypt password hashing."""
import bcrypt
import secrets


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_hex(32)