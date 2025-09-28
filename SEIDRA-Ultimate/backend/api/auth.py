"""
SEIDRA Authentication API
User management and JWT authentication
"""

import os
import jwt
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Optional, Any, cast
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from types import SimpleNamespace
from pydantic import BaseModel, Field, EmailStr
from passlib.context import CryptContext

from services.database import DatabaseService
from api.settings_models import SettingsResponse, DEFAULT_SETTINGS
from core.config import settings
from core.rate_limit import auth_rate_limit_dependencies

router = APIRouter(dependencies=auth_rate_limit_dependencies)

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET", "seidra-mystical-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def _serialize_created_at(value: Any | None) -> str:
    """Return an ISO 8601 representation of a ``created_at`` attribute."""

    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return datetime.utcnow().isoformat()

    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()

    return datetime.utcnow().isoformat()


def _fallback_user() -> SimpleNamespace:
    """Return a lightweight system user for development/test scenarios."""

    return SimpleNamespace(
        id=1,
        username="system",
        email="system@seidra.local",
        is_active=True,
        is_system=True,
        created_at=datetime.utcnow().isoformat(),
        settings=deepcopy(DEFAULT_SETTINGS),
    )

# Request/Response models
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    created_at: str
    settings: dict

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse

class TokenData(BaseModel):
    username: Optional[str] = None

# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    request: Any = None,
):
    """Verify JWT token.

    When ``SEIDRA_ALLOW_SYSTEM_FALLBACK`` is enabled and no valid token is
    supplied, a lightweight system user (flagged with ``is_system=True``) is
    returned so endpoints can operate in development environments without
    requiring authentication.
    """
    request_obj = cast(Optional[Request], request)

    if credentials is None:
        if settings.allow_system_fallback:
            fallback = _fallback_user()
            if request_obj is not None:
                request_obj.state.authenticated_user_id = fallback.id
            return fallback

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        if settings.allow_system_fallback:
            fallback = _fallback_user()
            if request_obj is not None:
                request_obj.state.authenticated_user_id = fallback.id
            return fallback

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    db = DatabaseService()
    try:
        user = db.get_user_by_username(token_data.username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if request_obj is not None:
            request_obj.state.authenticated_user_id = getattr(user, "id", None)
        return user
    finally:
        db.close()


# API endpoints
@router.post("/register", response_model=Token)
async def register_user(user_data: UserRegister, request: Request):
    """Register new user"""
    
    db = DatabaseService()
    try:
        # Check if user already exists
        existing_user = db.get_user_by_username(user_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )

        existing_email_user = db.get_user_by_email(user_data.email)
        if existing_email_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hash password
        hashed_password = get_password_hash(user_data.password)

        # Create user
        user = db.create_user(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password
        )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            created_at=_serialize_created_at(getattr(user, "created_at", None)),
            settings=user.settings or {}
        )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # in seconds
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )
    finally:
        db.close()

@router.post("/login", response_model=Token)
async def login_user(user_data: UserLogin, request: Request):
    """Login user"""
    
    db = DatabaseService()
    try:
        # Get user
        user = db.get_user_by_username(user_data.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        # Verify password
        if not verify_password(user_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled"
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            created_at=_serialize_created_at(getattr(user, "created_at", None)),
            settings=user.settings or {}
        )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # in seconds
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )
    finally:
        db.close()

@router.get("/me", response_model=UserResponse)
async def get_current_user(request: Request, current_user = Depends(verify_token)):
    """Get current user information"""
    
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=_serialize_created_at(getattr(current_user, "created_at", None)),
        settings=current_user.settings or {}
    )

@router.put("/me/settings", response_model=SettingsResponse)
async def update_user_settings(
    settings: dict,
    request: Request,
    current_user = Depends(verify_token)
):
    """Update user settings"""

    db = DatabaseService()
    try:
        user = db.update_user_settings(current_user.id, **settings)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        payload = {**DEFAULT_SETTINGS, **(user.settings or {})}
        extra = payload.get("extra", {})

        return SettingsResponse(
            theme=payload.get("theme", DEFAULT_SETTINGS["theme"]),
            language=payload.get("language", DEFAULT_SETTINGS["language"]),
            notifications=payload.get("notifications", DEFAULT_SETTINGS["notifications"]),
            telemetry_opt_in=payload.get("telemetry_opt_in", DEFAULT_SETTINGS["telemetry_opt_in"]),
            extra=extra,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )
    finally:
        db.close()

@router.post("/logout")
async def logout_user(request: Request, current_user = Depends(verify_token)):
    """Logout user (invalidate token)"""
    
    # In a production system, you would add the token to a blacklist
    # For now, just return success message
    
    return {"message": "Logged out successfully"}

@router.post("/refresh")
async def refresh_token(request: Request, current_user = Depends(verify_token)):
    """Refresh access token"""
    
    # Create new access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.username}, expires_delta=access_token_expires
    )
    
    user_response = UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=_serialize_created_at(getattr(current_user, "created_at", None)),
        settings=current_user.settings or {}
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response
    )

@router.delete("/me")
async def delete_account(request: Request, current_user = Depends(verify_token)):
    """Delete user account"""
    
    db = DatabaseService()
    try:
        # In production, implement proper account deletion
        # This would include deleting all user data, media files, etc.
        
        return {"message": "Account deletion requested"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )
    finally:
        db.close()
