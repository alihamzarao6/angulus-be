# ==============================================================================
# FILE: auth/utils.py
# DESCRIPTION: Authentication utilities (password hashing, JWT, email verification)
# ==============================================================================

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, status
from bson import ObjectId
import requests

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

# Email configuration
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
MAILGUN_BASE_URL = os.getenv("MAILGUN_BASE_URL", "https://api.mailgun.net/v3/")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@atlasprimebr.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> dict:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        return {"user_id": user_id}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

def generate_verification_token() -> str:
    """Generate a random verification token"""
    return secrets.token_urlsafe(32)

def send_email(to_email: str, subject: str, body: str, is_html: bool = False):
    """Send email using Mailgun"""
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        print(f"EMAIL SIMULATION - To: {to_email}, Subject: {subject}")
        return True
    
    try:
        url = f"{MAILGUN_BASE_URL}{MAILGUN_DOMAIN}/messages"
        auth = ("api", MAILGUN_API_KEY)
        data = {
            "from": f"Atlas Prime <{FROM_EMAIL}>",
            "to": to_email,
            "subject": subject,
            "html" if is_html else "text": body
        }
        
        response = requests.post(url, auth=auth, data=data, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Email sent successfully to {to_email}")
            return True
        else:
            print(f"❌ Failed to send email: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False

def send_verification_email(email: str, token: str):
    """Send email verification email"""
    verification_url = f"{BASE_URL}/auth/verify-email?token={token}"
    
    subject = "Verify Your Email Address"
    body = f"""
    <html>
    <body>
        <h2>Welcome to Our Platform!</h2>
        <p>Please click the link below to verify your email address:</p>
        <p><a href="{verification_url}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Verify Email</a></p>
        <p>Or copy and paste this link in your browser:</p>
        <p>{verification_url}</p>
        <p>This link will expire in 24 hours.</p>
        <p>If you didn't create an account, please ignore this email.</p>
    </body>
    </html>
    """
    
    return send_email(email, subject, body, is_html=True)

def send_password_reset_email(email: str, token: str):
    """Send password reset email"""
    reset_url = f"{BASE_URL}/auth/reset-password?token={token}"
    
    subject = "Reset Your Password"
    body = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>You requested to reset your password. Click the link below:</p>
        <p><a href="{reset_url}" style="background-color: #f44336; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
        <p>Or copy and paste this link in your browser:</p>
        <p>{reset_url}</p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this, please ignore this email.</p>
    </body>
    </html>
    """
    
    return send_email(email, subject, body, is_html=True)
