"""hash_password + verify_password."""
import hashlib
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"sha256${salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    test = hashlib.sha256((salt + password).encode()).hexdigest()
    return test == digest
