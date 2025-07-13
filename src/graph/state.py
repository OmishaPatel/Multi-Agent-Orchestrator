from typing import List, TypedDict, Optional, Dict, Annotated
from langgraph.graph.message import add_messages

#Output format for planning agent to generate
class SubTask(TypedDict):
    id: int
    type: str
    description: str
    dependencies: List[int]
    status: str
    result: Optional[str]

# main state dictionary to be passed between nodes
class AgentState(TypedDict):
    user_request: str
    plan: List[SubTask]
    task_results: Dict[int, str]
    next_task_id: Optional[int]
    messages: Annotated[list, add_messages]