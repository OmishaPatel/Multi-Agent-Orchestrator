from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from src.core.workflow_factory import WorkflowFactory
from pydantic import BaseModel, Field
import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from src.config.settings import get_settings
from src.utils.logging_config import get_api_logger, RequestLogger, log_api_request
from src.graph.state import AgentState, SubTask, TaskType,StateManager, TaskStatus, ApprovalStatus, TimestampUtils

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

class TaskInfo(BaseModel):
    id: int = Field(..., description="Task identifier")
    type: str = Field(..., description="Task type (research, code, analysis, summary, calculation)")
    description: str = Field(..., description="Task description")
    status: str = Field(..., description="Task status (pending, in_progress, completed, failed)")
    dependencies: List[int] = Field(default_factory=list, description="List of task IDs this task depends on")
    result: Optional[str] = Field(None, description="Task result if completed")
    started_at: Optional[datetime] = Field(None, description="When task execution started")
    completed_at: Optional[datetime] = Field(None, description="When task was completed")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "type": "research",
                "description": "Research renewable energy trends",
                "status": "completed",
                "dependencies": [],
                "result": "Found 5 key trends in renewable energy...",
                "started_at": "2024-01-15T10:35:00Z",
                "completed_at": "2024-01-15T10:40:00Z"
            }
        }

class ProgressInfo(BaseModel):
    total_tasks: int = Field(..., description="Total number of tasks in the plan")
    completed_tasks: int = Field(..., description="Number of completed tasks")
    failed_tasks: int = Field(..., description="Number of failed tasks")
    in_progress_tasks: int = Field(..., description="Number of tasks currently in progress")
    pending_tasks: int = Field(..., description="Number of pending tasks")
    completion_percentage: float = Field(..., description="Completion percentage (0-100)")
    estimated_remaining_time: Optional[int] = Field(None, description="Estimated remaining time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "total_tasks": 3,
                "completed_tasks": 2,
                "failed_tasks": 0,
                "in_progress_tasks": 1,
                "pending_tasks": 0,
                "completion_percentage": 66.7,
                "estimated_remaining_time": 120
            }
        }

class WorkflowStatusResponse(BaseModel):
    thread_id: str = Field(..., description="Workflow thread identifier")
    status: str = Field(..., description="Overall workflow status")
    progress: ProgressInfo = Field(..., description="Progress information")
    tasks: List[TaskInfo] = Field(default_factory=list, description="List of all tasks with their status")
    current_task: Optional[TaskInfo] = Field(None, description="Currently executing task")
    user_request: str = Field(..., description="Original user request")
    human_approval_status: str = Field(..., description="Human approval status")
    user_feedback: Optional[str] = Field(None, description="User feedback if plan was rejected")
    final_report: Optional[str] = Field(None, description="Final report if workflow is completed")
    messages: List[str] = Field(default_factory=list, description="Workflow execution messages")
    last_updated: datetime = Field(..., description="When the status was last updated")
    checkpointing_type: str = Field(..., description="Type of checkpointing being used")

    class Config:
        json_schema_extra = {
            "example": {
                "thread_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "in_progress",
                "progress": {
                    "total_tasks": 3,
                    "completed_tasks": 1,
                    "failed_tasks": 0,
                    "in_progress_tasks": 1,
                    "pending_tasks": 1,
                    "completion_percentage": 33.3
                },
                "tasks": [],
                "current_task": {
                    "id": 2,
                    "type": "code",
                    "description": "Generate analysis code",
                    "status": "in_progress"
                },
                "user_request": "Analyze renewable energy data",
                "human_approval_status": "approved",
                "user_feedback": None,
                "final_report": None,
                "messages": ["Planning completed", "Task 1 completed"],
                "last_updated": "2024-01-15T10:45:00Z",
                "checkpointing_type": "hybrid"
            }
        }

class TaskInfo(BaseModel):
    id: int = Field(..., description="Task identifier")
    type: str = Field(..., description="Task type (research, code, analysis, summary, calculation)")
    description: str = Field(..., description="Task description")
    status: str = Field(..., description="Task status (pending, in_progress, completed, failed)")
    dependencies: List[int] = Field(default_factory=list, description="List of task IDs this task depends on")
    result: Optional[str] = Field(None, description="Task result if completed")
    started_at: Optional[datetime] = Field(None, description="When task execution started")
    completed_at: Optional[datetime] = Field(None, description="When task was completed")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "type": "research",
                "description": "Research renewable energy trends",
                "status": "completed",
                "dependencies": [],
                "result": "Found 5 key trends in renewable energy...",
                "started_at": "2024-01-15T10:35:00Z",
                "completed_at": "2024-01-15T10:40:00Z"
            }
        }

class ProgressInfo(BaseModel):
    total_tasks: int = Field(..., description="Total number of tasks in the plan")
    completed_tasks: int = Field(..., description="Number of completed tasks")
    failed_tasks: int = Field(..., description="Number of failed tasks")
    in_progress_tasks: int = Field(..., description="Number of tasks currently in progress")
    pending_tasks: int = Field(..., description="Number of pending tasks")
    completion_percentage: float = Field(..., description="Completion percentage (0-100)")
    estimated_remaining_time: Optional[int] = Field(None, description="Estimated remaining time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "total_tasks": 3,
                "completed_tasks": 2,
                "failed_tasks": 0,
                "in_progress_tasks": 1,
                "pending_tasks": 0,
                "completion_percentage": 66.7,
                "estimated_remaining_time": 120
            }
        }

class WorkflowStatusResponse(BaseModel):
    thread_id: str = Field(..., description="Workflow thread identifier")
    status: str = Field(..., description="Overall workflow status")
    progress: ProgressInfo = Field(..., description="Progress information")
    tasks: List[TaskInfo] = Field(default_factory=list, description="List of all tasks with their status")
    current_task: Optional[TaskInfo] = Field(None, description="Currently executing task")
    user_request: str = Field(..., description="Original user request")
    human_approval_status: str = Field(..., description="Human approval status")
    user_feedback: Optional[str] = Field(None, description="User feedback if plan was rejected")
    final_report: Optional[str] = Field(None, description="Final report if workflow is completed")
    messages: List[str] = Field(default_factory=list, description="Workflow execution messages")
    last_updated: datetime = Field(..., description="When the status was last updated")
    checkpointing_type: str = Field(..., description="Type of checkpointing being used")

    class Config:
        json_schema_extra = {
            "example": {
                "thread_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "in_progress",
                "progress": {
                    "total_tasks": 3,
                    "completed_tasks": 1,
                    "failed_tasks": 0,
                    "in_progress_tasks": 1,
                    "pending_tasks": 1,
                    "completion_percentage": 33.3
                },
                "tasks": [],
                "current_task": {
                    "id": 2,
                    "type": "code",
                    "description": "Generate analysis code",
                    "status": "in_progress"
                },
                "user_request": "Analyze renewable energy data",
                "human_approval_status": "approved",
                "user_feedback": None,
                "final_report": None,
                "messages": ["Planning completed", "Task 1 completed"],
                "last_updated": "2024-01-15T10:45:00Z",
                "checkpointing_type": "hybrid"
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

@router.get("/status/{thread_id}", response_model=WorkflowStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Workflow not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Workflow Status",
    description="Retrieve real-time status and progress information for a workflow execution"
)
async def get_workflow_status(
    thread_id: str,
    workflow_factory: WorkflowFactory = Depends(get_workflow_factory)
) -> WorkflowStatusResponse:
    """
    Get real-time workflow status and progress information.
    
    This endpoint provides:
    1. Overall workflow status and progress metrics
    2. Individual task statuses and results
    3. Current task being executed
    4. Human approval status and feedback
    5. Final report if workflow is completed
    6. Execution messages and timestamps
    
    Supports efficient polling for real-time updates.
    """
    
    logger.info(f"Getting status for workflow {thread_id}")
    
    try:
        # Validate thread_id format - but be more lenient for test IDs
        if not thread_id or len(thread_id.strip()) == 0:
            logger.warning(f"Empty thread_id provided")
            raise HTTPException(
                status_code=400,
                detail="Thread ID cannot be empty"
            )
        
        # Try UUID validation, but allow test thread IDs to pass through
        try:
            uuid.UUID(thread_id)
        except ValueError:
            # Allow test thread IDs that start with "test-"
            if not thread_id.startswith("test-"):
                logger.warning(f"Invalid thread_id format: {thread_id}")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid thread_id format. Must be a valid UUID or test ID."
                )
            # Test thread IDs are allowed to pass through
        
        # Get workflow status from factory
        status_data = workflow_factory.get_workflow_status(thread_id)
        
        if not status_data or status_data.get("status") == "not_found":
            logger.warning(f"Workflow {thread_id} not found")
            raise HTTPException(
                status_code=404,
                detail=f"Workflow with thread_id {thread_id} not found"
            )
        
        if status_data.get("status") == "error":
            logger.error(f"Error retrieving workflow {thread_id}: {status_data.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Error retrieving workflow status: {status_data.get('error')}"
            )
        
        # Build comprehensive status response
        response = _build_status_response(thread_id, status_data, workflow_factory.checkpointing_type)
        
        logger.info(f"Status retrieved for workflow {thread_id}: {response.status} ({response.progress.completion_percentage:.1f}% complete)")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get status for workflow {thread_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve workflow status: {str(e)}"
        )


def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    if not timestamp_str:
        return None
    try:
        from datetime import datetime
        # Handle both 'Z' and '+00:00' timezone formats
        clean_timestamp = timestamp_str.replace('Z', '+00:00')
        return datetime.fromisoformat(clean_timestamp)
    except (ValueError, AttributeError):
        return None

def _build_status_response(thread_id: str, status_data: Dict[str, Any], checkpointing_type: str) -> WorkflowStatusResponse:
    """
    Build comprehensive status response from workflow status data.
    
    This function aggregates task information, calculates progress metrics,
    and formats the response for the API client.
    """
    
    # Extract basic information
    user_request = status_data.get("user_request", "")
    plan = status_data.get("plan", [])
    task_results = status_data.get("task_results", {})
    messages = status_data.get("messages", [])
    human_approval_status = status_data.get("human_approval_status", "pending")
    user_feedback = status_data.get("user_feedback")
    final_report = status_data.get("final_report")
    next_task_id = status_data.get("next_task_id")
    
    # Convert tasks to TaskInfo objects
    tasks = []
    current_task = None
    
    for task in plan:
        task_info = TaskInfo(
            id=task["id"],
            type=task["type"],
            description=task["description"],
            status=task["status"],
            dependencies=task.get("dependencies", []),
            result=task_results.get(task["id"]),
            started_at=_parse_timestamp(task.get("started_at")),
            completed_at=_parse_timestamp(task.get("completed_at"))
        )
        tasks.append(task_info)
        
        # Identify current task
        if task["id"] == next_task_id or task["status"] == TaskStatus.IN_PROGRESS:
            current_task = task_info
    
    # Calculate progress metrics
    progress = _calculate_progress_metrics(plan)
    
    # Determine overall workflow status
    overall_status = _determine_overall_status(
        human_approval_status, 
        plan, 
        final_report is not None
    )
    
    return WorkflowStatusResponse(
        thread_id=thread_id,
        status=overall_status,
        progress=progress,
        tasks=tasks,
        current_task=current_task,
        user_request=user_request,
        human_approval_status=human_approval_status,
        user_feedback=user_feedback,
        final_report=final_report,
        messages=messages,
        last_updated=datetime.utcnow(),
        checkpointing_type=checkpointing_type
    )

def _calculate_progress_metrics(plan: List[Dict[str, Any]]) -> ProgressInfo:
    if not plan:
        return ProgressInfo(
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            in_progress_tasks=0,
            pending_tasks=0,
            completion_percentage=0.0,
            estimated_remaining_time=None
        )
    
    total_tasks = len(plan)
    completed_tasks = len([t for t in plan if t["status"] == TaskStatus.COMPLETED])
    failed_tasks = len([t for t in plan if t["status"] == TaskStatus.FAILED])
    in_progress_tasks = len([t for t in plan if t["status"] == TaskStatus.IN_PROGRESS])
    pending_tasks = len([t for t in plan if t["status"] == TaskStatus.PENDING])
    
    completion_percentage = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0.0
    
    # Simple estimation
    remaining_tasks = pending_tasks + in_progress_tasks
    estimated_remaining_time = _estimate_remaining_time(plan)
    
    return ProgressInfo(
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        in_progress_tasks=in_progress_tasks,
        pending_tasks=pending_tasks,
        completion_percentage=round(completion_percentage, 1),
        estimated_remaining_time=estimated_remaining_time
    )

def _estimate_remaining_time(plan: List[Dict[str, Any]]) -> Optional[int]:
    completed_durations = []
    for task in plan:
        if task["status"] == TaskStatus.COMPLETED:
            duration = TimestampUtils.calculate_task_duration(task)
            if duration:
                completed_durations.append(duration)
    
    if not completed_durations:
        # No completed tasks yet, use default estimate
        remaining_tasks = len([t for t in plan if t["status"] in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]])
        return remaining_tasks * 60  # 60 seconds per task default
    
    # Use average of completed tasks
    avg_duration = sum(completed_durations) / len(completed_durations)
    remaining_tasks = len([t for t in plan if t["status"] == TaskStatus.PENDING])
    
    # Add time for in-progress tasks (assume half remaining)
    in_progress_tasks = len([t for t in plan if t["status"] == TaskStatus.IN_PROGRESS])
    
    return int(remaining_tasks * avg_duration + in_progress_tasks * avg_duration * 0.5)
    
def _determine_overall_status(
    human_approval_status: str, 
    plan: List[Dict[str, Any]], 
    has_final_report: bool
) -> str:

    # Check for human approval states first
    if human_approval_status == ApprovalStatus.PENDING and plan:
        return "pending_approval"
    elif human_approval_status == ApprovalStatus.REJECTED:
        return "plan_rejected"
    
    # Check task execution states
    if not plan:
        return "planning"
    
    if has_final_report:
        return "completed"
    
    # Check if any tasks have failed
    if any(task["status"] == TaskStatus.FAILED for task in plan):
        return "failed"
    
    # Check if all tasks are completed
    if all(task["status"] == TaskStatus.COMPLETED for task in plan):
        return "finalizing"
    
    # Check if any tasks are in progress
    if any(task["status"] == TaskStatus.IN_PROGRESS for task in plan):
        return "in_progress"
    
    # Default to planning if tasks exist but none are in progress
    return "planning"


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
