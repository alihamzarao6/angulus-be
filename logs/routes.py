from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId
from db import db
from json_parser import parse_mongo_documents, parse_mongo_document
from auth.dependencies import get_current_user
from logs.models import (
    LogsFilterRequest, LogsSummaryResponse, SystemStatusResponse,
    ActivityAction, ActivityLogResponse
)
from logs.utils import get_system_status, log_user_activity, cleanup_old_logs

router = APIRouter(tags=["Logs & Monitoring"])

@router.get("/status", response_model=SystemStatusResponse)
async def system_status():
    """
    System health check endpoint - Phase 1 requirement
    Returns system status and service health information
    """
    status_info = get_system_status()
    return SystemStatusResponse(**status_info)

@router.get("/logs", response_model=LogsSummaryResponse)
async def get_user_activity_logs(
    current_user: dict = Depends(get_current_user),
    action: Optional[ActivityAction] = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=200, description="Number of logs to return"),
    start_date: Optional[datetime] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date filter (ISO format)")
):
    """
    Get user activity logs with filtering options
    
    Query Parameters:
    - action: Filter by specific action type
    - limit: Number of logs to return (1-200, default: 50)
    - start_date: Filter logs after this date
    - end_date: Filter logs before this date
    """
    try:
        # Build query filter
        query_filter = {"user_id": str(current_user["_id"])}
        
        # Add action filter
        if action:
            query_filter["action"] = action.value
        
        # Add date range filters
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            query_filter["timestamp"] = date_filter
        
        # Get user's activity logs
        logs_cursor = db.activity_logs.find(
            query_filter,
            sort=[("timestamp", -1)],  # Most recent first
            limit=limit
        )
        logs = list(logs_cursor)
        
        # Get total count for this user
        total_logs = db.activity_logs.count_documents({"user_id": str(current_user["_id"])})
        
        # Get action summary (counts by action type)
        pipeline = [
            {"$match": {"user_id": str(current_user["_id"])}},
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        action_counts = list(db.activity_logs.aggregate(pipeline))
        action_summary = {item["_id"]: item["count"] for item in action_counts}
        
        # Convert logs to response format
        formatted_logs = []
        for log in logs:
            formatted_logs.append(ActivityLogResponse(
                id=str(log["_id"]),
                user_id=log["user_id"],
                action=log["action"],
                timestamp=log["timestamp"],
                details=log.get("details", {}),
                ip_address=log.get("ip_address"),
                user_agent=log.get("user_agent")
            ))
        
        return LogsSummaryResponse(
            total_logs=total_logs,
            returned_logs=len(formatted_logs),
            action_summary=action_summary,
            logs=formatted_logs
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve activity logs: {str(e)}"
        )

@router.get("/logs/actions")
async def get_available_actions(current_user: dict = Depends(get_current_user)):
    """Get list of all available action types for filtering"""
    return {
        "actions": [action.value for action in ActivityAction],
        "descriptions": {
            "user_registration": "User account creation",
            "email_verification": "Email address verification",
            "user_login": "User login events",
            "user_logout": "User logout events", 
            "password_reset_request": "Password reset requests",
            "password_reset_completed": "Completed password resets",
            "chat_message_sent": "Chat messages sent",
            "agent_created": "AI agent creation",
            "agent_updated": "AI agent modifications",
            "agent_deleted": "AI agent deletion",
            "agent_message_sent": "Direct agent interactions",
            "file_uploaded": "File upload events",
            "settings_updated": "Settings modifications",
            "logs_exported": "Log export events",
            "tools_accessed": "Tools page access"
        }
    }

@router.get("/logs/summary")
async def get_logs_summary(current_user: dict = Depends(get_current_user)):
    """Get summary statistics for user activity"""
    try:
        user_id = str(current_user["_id"])
        
        # Get activity counts by day (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        daily_pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": seven_days_ago}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp"
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        daily_activity = list(db.activity_logs.aggregate(daily_pipeline))
        
        # Get most recent activities (last 5)
        recent_logs = list(db.activity_logs.find(
            {"user_id": user_id},
            {"action": 1, "timestamp": 1, "details.content_length": 1},
            sort=[("timestamp", -1)],
            limit=5
        ))
        
        return {
            "daily_activity": daily_activity,
            "recent_activities": parse_mongo_documents(recent_logs),
            "total_activities": db.activity_logs.count_documents({"user_id": user_id})
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get logs summary: {str(e)}"
        )

@router.delete("/logs/cleanup")
async def cleanup_logs(
    current_user: dict = Depends(get_current_user),
    days_to_keep: int = Query(30, ge=1, le=365, description="Days of logs to keep")
):
    """
    Clean up old activity logs (admin function)
    Only removes logs older than specified days
    """
    try:
        deleted_count = cleanup_old_logs(days_to_keep)
        
        # Log this cleanup action
        log_user_activity(
            user_id=str(current_user["_id"]),
            action=ActivityAction.LOGS_EXPORTED,  # Reusing closest action
            details={
                "action": "logs_cleanup",
                "days_to_keep": days_to_keep,
                "deleted_count": deleted_count
            }
        )
        
        return {
            "success": True,
            "message": f"Cleaned up {deleted_count} old log entries",
            "deleted_count": deleted_count,
            "days_kept": days_to_keep
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup logs: {str(e)}"
        )
