# ==============================================================================
# DESCRIPTION: Utility functions for logging activities
# ==============================================================================

import os
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import Request
from db import db
from logs.models import ActivityAction

def extract_client_info(request: Request) -> Dict[str, str]:
    """Extract client IP and user agent from request"""
    return {
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown")
    }

def log_user_activity(
    user_id: str, 
    action: ActivityAction, 
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> bool:
    """
    Log user activity to the database
    
    Args:
        user_id: ID of the user performing the action
        action: Type of action performed
        details: Additional details about the action
        request: FastAPI request object for extracting client info
    
    Returns:
        bool: True if logging was successful, False otherwise
    """
    try:
        # Extract client information if request is provided
        client_info = extract_client_info(request) if request else {}
        
        # Create activity log entry
        activity_log = {
            "user_id": user_id,
            "action": action.value,
            "timestamp": datetime.utcnow(),
            "details": details or {},
            "ip_address": client_info.get("ip_address"),
            "user_agent": client_info.get("user_agent")
        }
        
        # Insert into database
        db.activity_logs.insert_one(activity_log)
        return True
        
    except Exception as e:
        print(f"Failed to log activity: {e}")
        return False

def get_system_status() -> Dict[str, Any]:
    """Get system health status"""
    try:
        # Test database connection
        try:
            db.users.find_one({}, {"_id": 1})
            db_status = "connected"
        except Exception:
            db_status = "disconnected"
        
        # Check OpenAI configuration
        openai_status = "configured" if os.getenv("OPENAI_API_KEY") else "not_configured"
        
        # Check email configuration
        email_status = "configured" if os.getenv("SMTP_USERNAME") else "not_configured"
        
        return {
            "status": "OK",
            "timestamp": datetime.utcnow(),
            "version": "1.0.0",
            "services": {
                "database": db_status,
                "openai": openai_status,
                "email": email_status,
                "authentication": "active"
            }
        }
        
    except Exception as e:
        return {
            "status": "ERROR",
            "timestamp": datetime.utcnow(),
            "version": "1.0.0",
            "error": str(e),
            "services": {
                "database": "error",
                "openai": "unknown",
                "email": "unknown", 
                "authentication": "unknown"
            }
        }

def cleanup_old_logs(days_to_keep: int = 30) -> int:
    """
    Clean up old activity logs
    
    Args:
        days_to_keep: Number of days to keep logs
    
    Returns:
        int: Number of logs deleted
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        result = db.activity_logs.delete_many({"timestamp": {"$lt": cutoff_date}})
        return result.deleted_count
    except Exception as e:
        print(f"Failed to cleanup logs: {e}")
        return 0