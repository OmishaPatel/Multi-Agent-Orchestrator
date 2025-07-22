from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolExecutor
from src.core.redis_saver import RedisCheckpointSaver
from src.core.state_recovery import StateRecoveryManager
from src.core.state import AgentState
import logging
import uuid

logger = logging.getLogger(__name__)

class WorkflowFactory:

    def __init__(self):
        self.checkpoint_saver = RedisCheckpointSaver()
        self.recovery_manager = StateRecoveryManager(self.checkpoint_saver)

    def create_workflow(self) -> StateGraph:

        #create the state graph
        workflow = StateGraph(AgentState)

        workflow.add_node("planning_agent", self._planning_node)
        workflow.add_node("research_agent", self._research_node)
        workflow.add_node("code_agent", self._code_node)
        workflow.add_node("await_approval", self._await_approval_node)


        #add edges
        workflow.add_edge("planning_agent", "await_approval")
        workflow.add_conditional_edges(
            "await_approval",
            self._should_continue,
            {
                "continue": "research_agent",
                "regenerate": "planning_agent",
                "end": "__end__"
            }

        )

        #entry point
        workflow.set_entry_point("planning_agent")

        #compile with redis checkpointing
        compiled_workflow = workflow.compile(
            checkpointer= self.checkpoint_saver,
            interrupt_before=["await_approval"]
        )

        logger.info("Created workflow with Redis checkpointing enabled")
        return compiled_workflow


    def _planning_node(self, state: AgentState) -> AgentState:
        #todo planning agent implementation
        return state

    def _research_node(self, state: AgentState) -> AgentState:
        #todo research agent implementation
        return state

    def _code_node(self, state: AgentState) -> AgentState:
        #todo code agent implementation
        return state

    def _await_approval_node(self, state: AgentState) -> AgentState:
        #todo will cause workflow to pause exceution resumes when/approve endpoint is called
        return state

    def _should_continue(self, state: AgentState) -> AgentState:
        approval_status = state.get("human_approval_status", "pending")
        if approval_status == "approved":
            return "continue"
        elif approval_status == "rejected":
            return "regenerate"

        else:
            return "end"

    def start_new_workflow(self, user_request:str, thread_id: str = None) -> Dict[str, Any]:
        if not thread_id:
            thread_id = str(uuid.uuidv4())

        workflow = self.create_workflow()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = workflow.invoke({"user_request": user_request}, config=config)
            return {"thread_id": thread_id, "result": result}
        except Exception as e:
            logger.error(f"Failed to start workflow: {e}")
            raise
    def continue_workflow(self, thread_id: str, new_input: Dict[str, Any]) -> Any:
        workflow = self.create_workflow()
        config = {"configurable": {"thread_id": thread_id}}

        try:
            #lang graph automatically loads latest checkpoint and continues
            result = workflow.invoke(new_input, config=config)
            return result
        except Exception as e:
            logger.error(f"Failed to continue workflow {thread_id}: {e}")
            raise

    def get_workflow_status(self, thread_id:str) -> Dict[str, Any]:
        try:
            state = self.recovery_manager.recover_latest_state(thread_id)
            if state:
                return {
                    "thread_id": thread_id,
                    "current_step": state.get("current_step", "unknown"),
                    "status": state.get("human_approval_status", "running"),
                    "plan": state.get("plan", []),
                    "partial_results": state.get("research_results", [])
                }
            return {"thread_id": thread_id, "status": "not_found"}
        except Exception as e:
            logger.error(f"Failed to get status for {thread_id}: {e}")
            return {"thread_id": thread_id, "status": "error", "error": str(e)}

