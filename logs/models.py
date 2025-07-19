# ==============================================================================
# Pydantic models for logs and activity tracking
# ==============================================================================

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class ActivityAction(str, Enum):
    """Enum for different types of user activities"""
    USER_REGISTRATION = "user_registration"
    EMAIL_VERIFICATION = "email_verification"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    CHAT_MESSAGE_SENT = "chat_message_sent"
    AGENT_CREATED = "agent_created"
    AGENT_UPDATED = "agent_updated"
    AGENT_DELETED = "agent_deleted"
    AGENT_MESSAGE_SENT = "agent_message_sent"
    FILE_UPLOADED = "file_uploaded"
    SETTINGS_UPDATED = "settings_updated"
    LOGS_EXPORTED = "logs_exported"
    TOOLS_ACCESSED = "tools_accessed"

class ActivityLogCreate(BaseModel):
    user_id: str
    action: ActivityAction
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class ActivityLogResponse(BaseModel):
    id: str
    user_id: str
    action: str
    timestamp: datetime
    details: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]

class LogsFilterRequest(BaseModel):
    action: Optional[ActivityAction] = None
    limit: Optional[int] = 50
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class LogsSummaryResponse(BaseModel):
    total_logs: int
    returned_logs: int
    action_summary: Dict[str, int]
    logs: List[ActivityLogResponse]

class SystemStatusResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    services: Dict[str, str]
    uptime: Optional[str] = None