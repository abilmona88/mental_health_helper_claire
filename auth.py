from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from db import User

# bcrypt only uses the first 72 bytes of a password.
# We enforce that ourselves so we never hit the backend error.
MAX_PASSWORD_BYTES = 72


def _truncate_password(password: str) -> bytes:
    """
    Encode the password as UTF-8 and truncate to bcrypt's 72-byte limit.
    Returns bytes ready for bcrypt.
    """
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > MAX_PASSWORD_BYTES:
        pw_bytes = pw_bytes[:MAX_PASSWORD_BYTES]
    return pw_bytes


def hash_password(password: str) -> str:
    """
    Hash the password using bcrypt, storing the result as a UTF-8 string.
    """
    pw_bytes = _truncate_password(password)
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    """
    try:
        pw_bytes = _truncate_password(plain_password)
        return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Look up a user by email (case-insensitive).
    """
    email = email.strip().lower()
    return db.query(User).filter(User.email == email).first()


def create_user(
    db: Session,
    email: str,
    full_name: str,
    password: str,
    profile_notes: str = "",
) -> User:
    """
    Create and persist a new user with a bcrypt-hashed password.
    """
    email = email.strip().lower()
    user = User(
        email=email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        profile_notes=profile_notes.strip() or None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
