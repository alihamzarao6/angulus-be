from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime, timedelta
from bson import ObjectId
from db import db
from json_parser import parse_mongo_document
from .models import (
    UserRegister, UserLogin, UserResponse, TokenResponse,
    EmailVerificationRequest, PasswordResetRequest, PasswordResetConfirm, EmailResendRequest
)
from .utils import (
    hash_password, verify_password, create_access_token,
    generate_verification_token, send_verification_email, send_password_reset_email
)
from .dependencies import get_current_user, get_current_user_optional

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=dict)
async def register_user(user_data: UserRegister):
    """Register a new user"""
    try:
        # Check if user already exists
        existing_user = db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Generate verification token
        verification_token = generate_verification_token()
        
        # Create user document
        user_doc = {
            "email": user_data.email,
            "username": user_data.username or user_data.email.split("@")[0],
            "password": hash_password(user_data.password),
            "is_verified": False,
            "verification_token": verification_token,
            "verification_token_expires": datetime.utcnow() + timedelta(hours=24),
            "created_at": datetime.utcnow(),
            "last_login": None,
            "is_active": True
        }
        
        # Insert user into database
        result = db.users.insert_one(user_doc)
        
        # Send verification email
        email_sent = send_verification_email(user_data.email, verification_token)
        
        # Log registration activity
        db.activity_logs.insert_one({
            "user_id": str(result.inserted_id),
            "action": "user_registration",
            "timestamp": datetime.utcnow(),
            "details": {"email": user_data.email, "email_sent": email_sent}
        })
        
        return {
            "success": True,
            "message": "User registered successfully. Please check your email to verify your account.",
            "email_sent": email_sent
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/verify-email")
async def verify_email(request: EmailVerificationRequest):
    """Verify user email with token"""
    try:
        # Find user with verification token
        user = db.users.find_one({
            "verification_token": request.token,
            "verification_token_expires": {"$gt": datetime.utcnow()}
        })
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )
        
        if user.get("is_verified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already verified"
            )
        
        # Update user as verified
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "is_verified": True,
                    "verified_at": datetime.utcnow()
                },
                "$unset": {
                    "verification_token": "",
                    "verification_token_expires": ""
                }
            }
        )
        
        # Log verification activity
        db.activity_logs.insert_one({
            "user_id": str(user["_id"]),
            "action": "email_verification",
            "timestamp": datetime.utcnow()
        })
        
        return {
            "success": True,
            "message": "Email verified successfully. You can now login."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email verification failed: {str(e)}"
        )

@router.post("/login", response_model=TokenResponse)
async def login_user(user_data: UserLogin):
    """Login user and return JWT token"""
    try:
        # Find user by email
        user = db.users.find_one({"email": user_data.email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Check if account is active
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )
        
        # Verify password
        if not verify_password(user_data.password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Check if email is verified
        if not user.get("is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please verify your email before logging in"
            )
        
        # Create access token
        access_token = create_access_token(data={"sub": str(user["_id"])})
        
        # Update last login
        db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        
        # Log login activity
        db.activity_logs.insert_one({
            "user_id": str(user["_id"]),
            "action": "user_login",
            "timestamp": datetime.utcnow()
        })
        
        # Prepare user response
        user_response = UserResponse(
            id=str(user["_id"]),
            email=user["email"],
            username=user.get("username"),
            is_verified=user["is_verified"],
            created_at=user["created_at"]
        )
        
        return TokenResponse(
            access_token=access_token,
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        username=current_user.get("username"),
        is_verified=current_user["is_verified"],
        created_at=current_user["created_at"]
    )

@router.post("/resend-verification")
async def resend_verification_email(request: EmailResendRequest):
    """Resend verification email - NO AUTH REQUIRED"""
    try:
        user = db.users.find_one({"email": request.email})
        
        # Always return success (don't reveal if email exists)
        if not user:
            return {
                "success": True, 
                "message": "If the email exists, verification link sent"
            }
        
        if user.get("is_verified"):
            return {
                "success": True,
                "message": "Email already verified. You can login now."
            }
        
        # Generate new verification token
        verification_token = generate_verification_token()
        
        # Update user
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "verification_token": verification_token,
                    "verification_token_expires": datetime.utcnow() + timedelta(hours=24)
                }
            }
        )
        
        # Send email
        send_verification_email(user["email"], verification_token)
        
        return {
            "success": True,
            "message": "If the email exists, verification link sent"
        }
        
    except Exception as e:
        raise HTTPException(500, f"Failed to resend verification: {str(e)}")

@router.post("/forgot-password")
async def forgot_password(request: PasswordResetRequest):
    """Send password reset email"""
    try:
        # Find user by email
        user = db.users.find_one({"email": request.email})
        
        # Always return success (don't reveal if email exists)
        if not user:
            return {
                "success": True,
                "message": "If the email exists, you will receive a password reset link"
            }
        
        # Generate reset token
        reset_token = generate_verification_token()
        
        # Update user with reset token
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "password_reset_token": reset_token,
                    "password_reset_expires": datetime.utcnow() + timedelta(hours=1)
                }
            }
        )
        
        # Send reset email
        email_sent = send_password_reset_email(user["email"], reset_token)
        
        # Log password reset request
        db.activity_logs.insert_one({
            "user_id": str(user["_id"]),
            "action": "password_reset_request",
            "timestamp": datetime.utcnow(),
            "details": {"email_sent": email_sent}
        })
        
        return {
            "success": True,
            "message": "If the email exists, you will receive a password reset link"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset failed: {str(e)}"
        )

@router.post("/reset-password")
async def reset_password(request: PasswordResetConfirm):
    """Reset password with token"""
    try:
        # Find user with reset token
        user = db.users.find_one({
            "password_reset_token": request.token,
            "password_reset_expires": {"$gt": datetime.utcnow()}
        })
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Update password
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "password": hash_password(request.new_password)
                },
                "$unset": {
                    "password_reset_token": "",
                    "password_reset_expires": ""
                }
            }
        )
        
        # Log password reset
        db.activity_logs.insert_one({
            "user_id": str(user["_id"]),
            "action": "password_reset_completed",
            "timestamp": datetime.utcnow()
        })
        
        return {
            "success": True,
            "message": "Password reset successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset failed: {str(e)}"
        )

@router.post("/logout")
async def logout_user(current_user: dict = Depends(get_current_user)):
    """Logout user (client should delete token)"""
    try:
        # Log logout activity
        db.activity_logs.insert_one({
            "user_id": str(current_user["_id"]),
            "action": "user_logout",
            "timestamp": datetime.utcnow()
        })
        
        return {
            "success": True,
            "message": "Logged out successfully"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )