"""
auth.py
Handles password hashing, JWT issuing/validation, and in-memory session
tracking (backed by database.py so accounts survive restarts).
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import JWTError, jwt

from models import UserInDB
import database

SECRET_KEY = os.getenv("SECRET_KEY", "insecure-dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False so page routes can handle "not logged in" with a redirect
# instead of a raw 401, while API routes still enforce auth via the
# dependencies below.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# ---------------------------------------------------------------------------
# In-memory state (loaded from / persisted to disk)
# ---------------------------------------------------------------------------
users_db: dict = database.load_users()
blacklisted_tokens: set = set()
active_sessions: dict = {}


def persist_users() -> None:
    database.save_users(users_db)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# User lookup
# ---------------------------------------------------------------------------
def get_user(username: str) -> Optional[UserInDB]:
    user = users_db.get(username)
    if user:
        return UserInDB(**user)
    return None


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_token(request: Request) -> Optional[str]:
    """Read the access token from the cookie (preferred) or Authorization header."""
    token = request.cookies.get("access_token")
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


def _decode_token(token: str) -> Optional[str]:
    """Returns the username ('sub' claim) if the token is valid, else None."""
    if not token or token in blacklisted_tokens:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


async def get_current_user(
    request: Request, token: Optional[str] = Depends(oauth2_scheme)
) -> UserInDB:
    """Strict dependency for API routes: raises 401 if not authenticated."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    cookie_token = request.cookies.get("access_token")
    actual_token = cookie_token or token
    username = _decode_token(actual_token) if actual_token else None
    if not username:
        raise credentials_exception
    user = get_user(username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: UserInDB = Depends(get_current_user),
) -> UserInDB:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_optional_user(request: Request) -> Optional[UserInDB]:
    """Lenient lookup for HTML page routes: returns None instead of raising,
    so the route itself can decide to redirect to /login."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    username = _decode_token(token)
    if not username:
        return None
    return get_user(username)
