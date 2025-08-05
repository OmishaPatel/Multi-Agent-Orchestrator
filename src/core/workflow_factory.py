from typing import Dict, Any, Optional
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from src.core.redis_state_manager import RedisStateManager
from src.graph.state import AgentState, StateManager
from src.graph.workflow import IntelligentWorkflowGraph
from src.config.settings import get_settings
from src.utils.logging_config import get_service_logger
import logging
import uuid

logger = get_service_logger("workflow_factory")

class WorkflowFactory:

    def __init__(self):
        self.settings = get_settings()
        
        # Initialize checkpointing based on configuration
        if self.settings.REDIS_ENABLED and self.settings.ENABLE_CHECKPOINTING:
            try:
                # Use memory checkpointing for LangGraph + Redis for state persistence
                self.checkpoint_saver = MemorySaver()
                self.redis_state_manager = RedisStateManager()
                self.checkpointing_enabled = True
                self.checkpointing_type = "hybrid"  # Memory + Redis
                logger.info("Initialized with hybrid checkpointing (Memory + Redis state)")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis state manager: {e}")
                logger.info("Falling back to memory checkpointing only")
                self.checkpoint_saver = MemorySaver()
                self.redis_state_manager = None
                self.checkpointing_enabled = True
                self.checkpointing_type = "memory"
        elif self.settings.ENABLE_CHECKPOINTING:
            self.checkpoint_saver = MemorySaver()
            self.redis_state_manager = None
            self.checkpointing_enabled = True
            self.checkpointing_type = "memory"
            logger.info("Initialized with memory checkpointing")
        else:
            self.checkpoint_saver = None
            self.redis_state_manager = None
            self.checkpointing_enabled = False
            self.checkpointing_type = "none"
            logger.info("Checkpointing disabled")
        
        self.workflow_graph = IntelligentWorkflowGraph()

    def create_workflow(self) -> StateGraph:
        """Create the intelligent workflow with configurable checkpointing"""
        
        try:
            logger.info("Starting workflow creation...")
            
            # Create the workflow graph
            logger.info("Creating workflow graph...")
            workflow = self.workflow_graph.create_workflow()
            logger.info("Workflow graph created successfully")
            
            # Compile with appropriate checkpointing
            logger.info("Compiling workflow...")
            if self.checkpointing_enabled:
                compiled_workflow = workflow.compile(
                    checkpointer=self.checkpoint_saver,
                    interrupt_before=["await_approval"]  # Pause for human approval
                )
                logger.info(f"Created intelligent workflow with {self.checkpointing_type} checkpointing enabled")
            else:
                compiled_workflow = workflow.compile()
                logger.info("Created intelligent workflow without checkpointing")
            
            return compiled_workflow
            
        except Exception as e:
            logger.error(f"Workflow creation failed at step: {e}", exc_info=True)
            raise

    def start_new_workflow(self, user_request:str, thread_id: str = None) -> Dict[str, Any]:
        if not thread_id:
            thread_id = str(uuid.uuid4())

        workflow = self.create_workflow()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = workflow.invoke({"user_request": user_request}, config=config)
            
            # Save state to Redis if using hybrid checkpointing
            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                self.redis_state_manager.save_state(thread_id, result)
            
            return {"thread_id": thread_id, "result": result}
        except Exception as e:
            logger.error(f"Failed to start workflow: {e}")
            raise
    def continue_workflow(self, thread_id: str, new_input: Dict[str, Any]) -> Any:
        workflow = self.create_workflow()
        config = {"configurable": {"thread_id": thread_id}}

        try:
            # For Redis checkpointing, use stream for better control over continuation
            if self.checkpointing_type == "redis":
                logger.info(f"Continuing Redis-checkpointed workflow {thread_id}")
                result = None
                for chunk in workflow.stream(new_input, config=config):
                    if chunk:
                        result = chunk
                return result
            else:
                # For memory checkpointing, use invoke
                result = workflow.invoke(new_input, config=config)
                return result
        except ValueError as e:
            if "No tasks to run in graph" in str(e):
                logger.warning(f"No tasks to run for workflow {thread_id}, attempting to get current state")
                # Try to get the current state to understand what's happening
                try:
                    current_state = workflow.get_state(config)
                    logger.info(f"Current workflow state: {current_state}")
                    return current_state.values if current_state else None
                except Exception as state_e:
                    logger.error(f"Failed to get workflow state: {state_e}")
                    raise e
            else:
                raise e
        except Exception as e:
            logger.error(f"Failed to continue workflow {thread_id}: {e}")
            raise

    def resume_after_approval(self, thread_id: str, approval_status: str, feedback: str = None) -> Any:
        """Resume workflow after human approval with proper state handling"""
        workflow = self.create_workflow()
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # For hybrid checkpointing, restore state from Redis first
            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                redis_state = self.redis_state_manager.get_state(thread_id)
                if redis_state:
                    logger.info(f"Restoring state from Redis for thread {thread_id}")
                    # Update the workflow state with Redis data
                    workflow.update_state(config, redis_state)
            
            # Update state with approval status
            workflow.update_state(config, {
                "human_approval_status": approval_status,
                "user_feedback": feedback
            })
            
            # Continue workflow
            logger.info(f"Resuming {self.checkpointing_type}-checkpointed workflow {thread_id} after approval")
            
            result = None
            try:
                for chunk in workflow.stream(None, config=config):
                    if chunk:
                        result = chunk
                        # Log progress for debugging
                        for node_name, node_result in chunk.items():
                            logger.debug(f"Executed node {node_name}")
                            if node_result and isinstance(node_result, dict) and 'plan' in node_result:
                                logger.info(f"Node {node_name} has plan with {len(node_result['plan'])} tasks")
                
                # Save final state to Redis if using hybrid checkpointing
                if result and self.checkpointing_type == "hybrid" and self.redis_state_manager:
                    self.redis_state_manager.save_state(thread_id, result)
                
                return result
            except Exception as stream_e:
                logger.warning(f"Stream approach failed: {stream_e}, trying invoke")
                # Fallback to invoke
                result = workflow.invoke(None, config=config)
                
                # Save final state to Redis if using hybrid checkpointing
                if result and self.checkpointing_type == "hybrid" and self.redis_state_manager:
                    self.redis_state_manager.save_state(thread_id, result)
                
                return result
                
        except ValueError as e:
            if "No tasks to run in graph" in str(e):
                logger.error(f"No tasks to run after approval for workflow {thread_id}")
                # Get current state for debugging
                try:
                    current_state = workflow.get_state(config)
                    if current_state:
                        logger.info(f"Current state after approval:")
                        logger.info(f"  - Next node: {current_state.next}")
                        logger.info(f"  - Values keys: {list(current_state.values.keys()) if current_state.values else 'None'}")
                        if current_state.values and 'plan' in current_state.values:
                            plan = current_state.values['plan']
                            logger.info(f"  - Plan has {len(plan)} tasks")
                            for task in plan:
                                logger.info(f"    Task {task['id']}: {task['description']} [{task['status']}]")
                        return current_state.values
                    else:
                        logger.error("No current state found")
                        return None
                except Exception as state_e:
                    logger.error(f"Failed to get state after approval error: {state_e}")
                    raise e
            else:
                raise e
        except Exception as e:
            logger.error(f"Failed to resume workflow {thread_id} after approval: {e}")
            raise

    def get_workflow_status(self, thread_id: str) -> Dict[str, Any]:
        """Get workflow status with fallback for different checkpointing modes"""
        try:
            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                # Hybrid checkpointing - get state from Redis
                state = self.redis_state_manager.get_state(thread_id)
                if state:
                    return {
                        "thread_id": thread_id,
                        "status": state.get("human_approval_status", "running"),
                        "plan": state.get("plan", []),
                        "task_results": state.get("task_results", {}),
                        "next_task_id": state.get("next_task_id"),
                        "checkpointing": self.checkpointing_type
                    }
            elif self.checkpointing_enabled:
                # Memory checkpointing - limited status info
                return {
                    "thread_id": thread_id,
                    "status": "running",
                    "checkpointing": self.checkpointing_type,
                    "note": "Limited status info available with memory checkpointing"
                }
            
            # Fallback for no checkpointing or failed recovery
            return {
                "thread_id": thread_id, 
                "status": "not_found",
                "checkpointing": self.checkpointing_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get status for {thread_id}: {e}")
            return {
                "thread_id": thread_id, 
                "status": "error", 
                "error": str(e),
                "checkpointing": self.checkpointing_type
            }

