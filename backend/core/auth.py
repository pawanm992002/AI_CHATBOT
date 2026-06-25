import os
import hashlib
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

security = HTTPBearer()

ALGORITHM = "HS256"

COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = 604800  # 7 days in seconds

limiter = Limiter(key_func=get_remote_address)

client = AsyncIOMotorClient(settings.MONGODB_URI)
db = client[settings.MONGODB_DB_NAME]

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60 * 24 * 7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def set_auth_cookie(response: Response, token: str, request: Request = None):
    secure = settings.COOKIE_SECURE
    samesite = settings.COOKIE_SAMESITE

    if request:
        is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        if not is_secure:
            secure = False
            if samesite == "none":
                samesite = "lax"

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )

def clear_auth_cookie(response: Response, request: Request = None):
    secure = settings.COOKIE_SECURE
    samesite = settings.COOKIE_SAMESITE

    if request:
        is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        if not is_secure:
            secure = False
            if samesite == "none":
                samesite = "lax"

    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure,
        samesite=samesite,
    )

async def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        role: str = payload.get("role")
        if sub is None or role is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return {"sub": sub, "role": role}

async def get_current_tenant(request: Request):
    user = await get_current_user(request)
    if user["role"] != "tenant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    tenant = await db.tenants.find_one({"tenant_id": user["sub"]})
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found",
        )
    
    status_val = tenant.get("status", "approved")
    if status_val == "disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is disabled",
        )
    elif status_val == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your registration is pending approval",
        )
    elif status_val == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your registration has been rejected",
        )
        
    return tenant

async def get_current_admin(request: Request):
    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return {"username": "admin", "role": "admin"}

async def verify_api_key(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    api_key = credentials.credentials
    if not api_key.startswith("sk_live_"):
        raise HTTPException(status_code=403, detail="Invalid API Key format")

    tenant = await db.tenants.find_one({"api_key": api_key})
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    status_val = tenant.get("status", "approved")
    if status_val == "disabled":
        raise HTTPException(status_code=403, detail="Tenant is disabled")
    elif status_val != "approved":
        raise HTTPException(status_code=403, detail="Tenant is not active")

    origin = request.headers.get("origin")
    if origin and settings.ENFORCE_DOMAIN and "localhost" not in origin:
        if tenant["domain"] not in origin:
            raise HTTPException(status_code=403, detail="Domain not allowed")

    return tenant
