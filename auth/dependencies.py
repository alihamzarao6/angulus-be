# ==============================================================================
# FILE: auth/dependencies.py
# DESCRIPTION: FastAPI dependencies for authentication
# ==============================================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from db import db
from .utils import verify_token
from .models import UserResponse

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current authenticated user"""
    token = credentials.credentials
    payload = verify_token(token)
    user_id = payload["user_id"]
    
    # Get user from database
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified"
        )
    
    return user

async def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current user but don't require verification (for some endpoints)"""
    token = credentials.credentials
    payload = verify_token(token)
    user_id = payload["user_id"]
    
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user
