from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from src.core.workflow_factory import WorkflowFactory
from pydantic import BaseModel, Field
import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional
from src.config.settings import get_settings
from src.utils.logging_config import get_api_logger, RequestLogger, log_api_request

router = APIRouter()
logger = get_api_logger("workflow")


class RunRequest(BaseModel):
    user_request: str = Field(..., min_length=1, max_length=5000,
    description="The user's request to be processed by AI system")

    class Config:
        json_schema_extra = {
            "example": {
                "user_request": "Research the latest trends in renewable energy and create a summary report"
            }
        }


class RunResponse(BaseModel):
    thread_id: str = Field(..., description="Unique identifier for the workflow execution")
    status: str = Field(..., description="Initial status of the workflow")
    message: str = Field(..., description="Human-readable status message")
    created_at: datetime = Field(..., description="Timestamp when workflow was initialized")

    class Config:
        json_schema_extra = {
            "example": {
                "thread_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "initiated",
                "message": "Workflow started successfully. Planning phase in progress.",
                "created_at": "2024-01-15T10:30:00Z"
            }
        }
class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    thread_id: Optional[str] = Field(None, description="Thread ID if available")

    class Config:
        json_schema_extra = {
                "example": {
                "error": "Workflow initiation failed",
                "details": "Redis connection unavailable",
                "thread_id": None
            }
        }

def get_workflow_factory() -> WorkflowFactory:
    return WorkflowFactory()


@router.post("/run", response_model=RunResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        },
        summary="Initialize AI Workflow",
        description="Start a new AI workflow execution with provided user resuqest"
    )
async def run_workflow(
    request: RunRequest,
    background_tasks: BackgroundTasks,
    workflow_factory: WorkflowFactory = Depends(get_workflow_factory)) -> RunResponse:

    """
    Initiate a new AI workflow execution.
    
    This endpoint:
    1. Validates the user request
    2. Generates a unique thread ID
    3. Initializes the workflow state
    4. Starts the LangGraph workflow execution
    5. Returns the thread ID for status tracking
    
    The workflow will run in the background and can be monitored via the /status endpoint.
    """

    thread_id = str(uuid.uuid4())
    
    logger.info(f"Initiating workflow for thread {thread_id}")
    logger.info(f"User request: {request.user_request[:100]}...")
    
    try:
        if len(request.user_request.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="User request cannot be empty"
            )
        
        # Start workflow execution in background
        background_tasks.add_task(
            execute_workflow_background,
            workflow_factory,
            request.user_request,
            thread_id
        )
        
        logger.info(f"Workflow {thread_id} initiated successfully")
        
        return RunResponse(
            thread_id=thread_id,
            status="initiated",
            message="Workflow started successfully. Planning phase in progress.",
            created_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate workflow {thread_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate workflow: {str(e)}"
        )

async def execute_workflow_background(
    workflow_factory: WorkflowFactory,
    user_request: str,
    thread_id: str
) -> None:
    """
    Execute workflow in background task.
    
    This function runs the actual workflow execution asynchronously,
    allowing the /run endpoint to return immediately while the workflow
    processes in the background.
    """
    
    logger.info(f"Starting background execution for workflow {thread_id}")
    
    try:
        result = workflow_factory.start_new_workflow(
            user_request=user_request,
            thread_id=thread_id
        )
        
        logger.info(f"Workflow {thread_id} completed successfully")
        logger.debug(f"Workflow result keys: {list(result.get('result', {}).keys()) if result.get('result') else 'No result'}")
        
    except Exception as e:
        logger.error(f"Background workflow execution failed for {thread_id}: {str(e)}", exc_info=True)
        # Optionally save error state to Redis if available
        try:
            if (workflow_factory.checkpointing_type == "hybrid" and 
                workflow_factory.redis_state_manager):
                
                error_state = {
                    "user_request": user_request,
                    "plan": [],
                    "task_results": {},
                    "next_task_id": None,
                    "messages": [f"Workflow failed: {str(e)}"],
                    "human_approval_status": "failed",
                    "user_feedback": None,
                    "final_report": f"Workflow execution failed: {str(e)}"
                }
                
                workflow_factory.redis_state_manager.save_state(thread_id, error_state)
                logger.info(f"Saved error state for workflow {thread_id}")
                
        except Exception as save_e:
            logger.error(f"Failed to save error state for {thread_id}: {save_e}")

@router.get("/cleanup/status")
async def get_cleanup_status():
    return cleanup_service.get_status()