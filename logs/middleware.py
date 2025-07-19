# ==============================================================================
# DESCRIPTION: Middleware for automatic activity logging
# ==============================================================================

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from logs.utils import log_user_activity
from logs.models import ActivityAction
import time
import json

class ActivityLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically log certain user activities"""
    
    def __init__(self, app, log_requests: bool = True):
        super().__init__(app)
        self.log_requests = log_requests
        
        # Define which endpoints to automatically log
        self.logged_endpoints = {
            "/auth/login": ActivityAction.USER_LOGIN,
            "/auth/logout": ActivityAction.USER_LOGOUT,
            "/tools": ActivityAction.TOOLS_ACCESSED,
            "/log-exports": ActivityAction.LOGS_EXPORTED,
            "/message": ActivityAction.AGENT_MESSAGE_SENT,
        }
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log specific endpoints if successful
        if (response.status_code < 400 and 
            self.log_requests and 
            request.url.path in self.logged_endpoints):
            
            try:
                # Try to get user info from response or request state
                user_id = getattr(request.state, 'user_id', None)
                
                if user_id:
                    log_user_activity(
                        user_id=user_id,
                        action=self.logged_endpoints[request.url.path],
                        details={
                            "endpoint": request.url.path,
                            "method": request.method,
                            "status_code": response.status_code,
                            "process_time": round(process_time, 3)
                        },
                        request=request
                    )
            except Exception as e:
                print(f"Middleware logging error: {e}")
        
        # Add process time header
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
