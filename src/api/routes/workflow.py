from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import uuid
import time

from src.config.settings import get_settings
from src.utils.logging_config import get_api_logger, RequestLogger, log_api_request

router = APIRouter()
logger = get_api_logger("workflow")


class RunRequest(BaseModel):
    """Request model for workflow execution."""
    request: str
    thread_id: str = None


class RunResponse(BaseModel):
    """Response model for workflow execution."""
    thread_id: str
    status: str


@router.post("/run", response_model=RunResponse)
async def run_workflow(request: RunRequest):
    """
    Start a new workflow execution.
    This is a placeholder that will be implemented in future tasks.
    """
    start_time = time.time()
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # Use request logging context
    with RequestLogger(thread_id, logger):
        try:
            logger.info(f"Workflow execution requested: {request.request[:100]}...")
            
            # This is just a placeholder - actual implementation will come in later tasks
            result = {
                "thread_id": thread_id,
                "status": "started",
            }
            
            logger.info(f"Workflow started successfully for thread: {thread_id}")
            
            # Log API request
            duration = time.time() - start_time
            log_api_request("POST", "/run", 200, duration, thread_id)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to start workflow: {e}", exc_info=True)
            duration = time.time() - start_time
            log_api_request("POST", "/run", 500, duration, thread_id)
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/cleanup/status")
async def get_cleanup_status():
    return cleanup_service.get_status()