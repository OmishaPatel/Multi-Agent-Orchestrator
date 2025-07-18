from typing import List, TypedDict, Optional, Dict, Annotated, Literal
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, validator
from datetime import datetime

#Output format for planning agent to generate
class SubTask(TypedDict):
    id: int
    type: str # 'research', 'code', 'analysis', 'summary', 'calculation'
    description: str
    dependencies: List[int]
    status: str # 'pending', 'in_progress', 'completed', 'failed'
    result: Optional[str]

# main state dictionary to be passed between nodes
class AgentState(TypedDict):
    user_request: str
    plan: List[SubTask]
    task_results: Dict[int, str]
    next_task_id: Optional[int]
    messages: Annotated[list, add_messages]
    # human approval fields
    human_approval_status: str # 'pending', 'approved', 'rejected'
    user_feedback: Optional[str]
    final_report: Optional[str]


# Validation

class AgentStateValidator(BaseModel):
    user_request: str = Field(..., min_length=1, description="Original user request")
    plan: List[SubTask] = Field(default_factory=list, description="List of subtasks")
    task_results: Dict[int, str] = Field(default_factory=dict, description="Results by task ID")
    next_task_id: Optional[int] = Field(None, description="Next task to execute")

    human_approval_status: Literal['pending', 'approved', 'rejected'] = Field(default='pending', description="Status of human approval for the plan")

    user_feedback: Optional[str] = Field(None, description="User feedback for plan refinement when rejected")

    final_report: Optional[str] = Field(None, description="Final compiled report when workflow is complete")

    @validator('plan')
    def validate_plan_structure(cls, v):
        if not v:
            return v

        task_ids = {task['id'] for task in v}

        for task in v:
            required_fields = ['id', 'type', 'description', 'dependencies', 'status']
            for field in required_fields:
                if field not in task:
                    raise ValueError(f"Task {task.get('id', 'unknown')} missing required field: {field}")
            valid_types = ['research', 'code', 'analysis', 'summary', 'calculation']
            if task['type'] not in valid_types:
                raise ValueError(f"Invalid task type: {task['type']}. Must be one of {valid_types}")
            
            # Validate status
            valid_statuses = ['pending', 'in_progress', 'completed', 'failed']
            if task['status'] not in valid_statuses:
                raise ValueError(f"Invalid task status: {task['status']}. Must be one of {valid_statuses}")

            for dep_id in task['dependencies']:
                if dep_id not in task_ids:
                    raise ValueError(f"Task {task['id']} has invalid dependency: {dep_id}")
        return v
    
    @validator('user_feedback')
    def validate_feedback_when_rejected(cls, v, values):
        approval_status = values.get('human_approval_status')
        if approval_status == 'rejected' and not v:
            raise ValueError("User feedback is required when plan is rejected")
        return v

    @validator('next_task_id')
    def validate_next_task_exists(cls, v, values):
        if v is None:
            return v
        plan = values.get('plan', [])
        task_ids = {task['id'] for task in plan}

        if v not in task_ids:
            raise ValueError(f"next_task_id {v} does not exist in plan")
        return v
    
# State Management Utilities
class StateManager:

    @staticmethod
    def create_initial_state(user_request: str) -> AgentState:
        return AgentState(
            user_request=user_request,
            plan=[],
            task_results={},
            next_task_id=None,
            messages=[],
            human_approval_status='pending',
            user_feedback=None,
            final_report=None
        )

    @staticmethod
    def validate_state(state: AgentState) -> bool:
        try:
            # convert TypedDict to dict for Pydantic validation
            state_dict = dict(state)
            # Remove messages field as it's handled by LangGraph
            state_dict.pop('messages', None)

            AgentStateValidator(**state_dict)
            return True
        except Exception as e:
            print(f"State validation eror: {e}")
            return False

    @staticmethod
    def update_approval_status(state: AgentState, status: Literal['approved', 'rejected'], feedback: Optional[str] = None) -> AgentState:
        if status == 'rejected' and not feedback:
            raise ValueError("Feedback is required when rejecting a plan")

        new_state = state.copy()
        new_state['human_approval_status'] = status
        new_state['user_feedback'] = feedback

        return new_state

    @staticmethod
    def set_final_report(state: AgentState, report:str) -> AgentState:
        new_state = state.copy()
        new_state['final_report'] = report
        return new_state

    @staticmethod
    def get_pending_tasks(state: AgentState) -> List[SubTask]:
        return [task for task in state['plan'] if task['status'] == 'pending']

    @staticmethod
    def get_completed_tasks(state: AgentState) -> List[SubTask]:
        return [task for task in state['plan'] if task['status'] == 'completed']

    @staticmethod
    def calculate_progress(state: AgentState) -> float:
        if not state['plan']:
            return 0.0
        
        completed = len([task for task in state['plan'] if task['status'] == 'completed'])
        total = len(state['plan'])
        
        return completed / total
    
    @staticmethod
    def is_workflow_complete(state: AgentState) -> bool:
        if not state['plan']:
            return False
        
        return all(task['status'] == 'completed' for task in state['plan'])
    
    @staticmethod
    def needs_human_approval(state: AgentState) -> bool:
        return (
            state['human_approval_status'] == 'pending' and 
            len(state['plan']) > 0
        )

# State Field Value Constants
class ApprovalStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

class TaskStatus:
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'

class TaskType:
    RESEARCH = 'research'
    CODE = 'code'
    ANALYSIS = 'analysis'
    SUMMARY = 'summary'
    CALCULATION = 'calculation'


