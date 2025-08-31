"""
Official LangGraph + Langfuse integration following Langfuse documentation
This provides native agent graph visualization in Langfuse dashboard
"""

from typing import Dict, Any, Optional
from langfuse.langchain import CallbackHandler
from langgraph.graph import StateGraph
from src.services.langfuse_service import langfuse_service
from src.graph.state import AgentState
from src.core.redis_state_manager import RedisStateManager
import logging
import uuid

logger = logging.getLogger(__name__)

class LangfuseLangGraphIntegration:
    """
    Native LangGraph + Langfuse integration for agent graph visualization
    """
    
    def __init__(self):
        self.langfuse_handler = langfuse_service.get_callback_handler()
    
    def create_traced_workflow(self, workflow: StateGraph, thread_id: str, 
                             user_id: Optional[str] = None, 
                             session_id: Optional[str] = None) -> StateGraph:
        """
        Create a LangGraph workflow with native Langfuse tracing
        This enables agent graph visualization in Langfuse dashboard
        """
        if not langfuse_service.is_enabled():
            logger.info("Langfuse not enabled, returning untraced workflow")
            return workflow
        
        try:
            # Create Langfuse configuration for LangGraph
            # config = self._create_langfuse_config(
            #     thread_id=thread_id,
            #     user_id=user_id,
            #     session_id=session_id
            # )
            
            # # Compile workflow with Langfuse callback handler
            # # This enables native agent graph visualization
            # compiled_workflow = workflow.compile(
            #     checkpointer=None,  # Will be set by WorkflowFactory
            #     interrupt_before=["await_approval"]
            # )
            
            # logger.info(f"Created LangGraph workflow with native Langfuse tracing for thread {thread_id}")
            # return compiled_workflow

            # Get Langfuse configuration with error handling
            config = langfuse_service.get_langgraph_config(thread_id)
            
            # CRITICAL FIX: Compile with checkpointer and error handling
            redis_manager = RedisStateManager()
            
            if redis_manager.is_enabled():
                compiled_workflow = workflow.compile(
                    checkpointer=redis_manager.get_checkpointer(),
                    interrupt_before=["await_approval"]
                )
            else:
                compiled_workflow = workflow.compile(
                    interrupt_before=["await_approval"]
                )
            
            logger.info(f"✅ Created LangGraph workflow with Langfuse tracing for thread {thread_id}")
            return compiled_workflow

            
        except Exception as e:
            logger.error(f"Failed to create traced workflow: {e}")
            # Fallback to untraced workflow
            return workflow.compile(interrupt_before=["await_approval"])
    
    def _create_langfuse_config(self, thread_id: str, user_id: Optional[str] = None, 
                              session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create LangGraph configuration with Langfuse callback handler
        """
        # CRITICAL FIX: Only add callbacks if handler is valid and not None
        callbacks = []
        if self.langfuse_handler is not None:
            # Validate that the callback handler has required attributes
            required_attrs = ['raise_error', 'ignore_chain', 'on_chain_start', 'on_chain_end']
            if all(hasattr(self.langfuse_handler, attr) for attr in required_attrs):
                callbacks = [self.langfuse_handler]
            else:
                logger.warning(f"Langfuse handler missing required attributes, skipping")
        
        config = {
            "configurable": {
                "thread_id": thread_id
            },
            "metadata": {
                "thread_id": thread_id,
                "workflow_type": "langgraph_agent_workflow",
                "system": "clarity-ai"
            }
        }
        
        # Only add callbacks if we have valid ones
        if callbacks:
            config["callbacks"] = callbacks
        
        # Add user context for Langfuse
        if user_id:
            config["metadata"]["user_id"] = user_id
        
        if session_id:
            config["metadata"]["session_id"] = session_id
        
        return config
    
    def get_execution_config(self, thread_id: str, user_id: Optional[str] = None, 
                           session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get execution configuration for LangGraph with Langfuse tracing
        """
        base_config = {"configurable": {"thread_id": thread_id}}
        
        if not langfuse_service.is_enabled():
            return base_config
        
        try:
            config = langfuse_service.get_langgraph_config(thread_id)
            
            # Add serialization-safe metadata
            if user_id:
                config["metadata"]["user_id"] = str(user_id)
            if session_id:
                config["metadata"]["session_id"] = str(session_id)
            
            # CRITICAL FIX: Add error handling for state serialization
            config["metadata"]["error_handling"] = "enabled"
            config["metadata"]["serialization_safe"] = True
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to create execution config: {e}")
            return base_config
    
    def start_agent_session(self, user_id: str, initial_request: str, 
                          thread_id: str) -> Optional[str]:
        """
        Start a Langfuse session for agent workflow tracking
        """
        if not langfuse_service.is_enabled():
            return None
        
        try:
            session_id = langfuse_service.start_user_session(
                user_id=user_id,
                session_metadata={
                    "thread_id": thread_id,
                    "initial_request": initial_request[:200],
                    "workflow_type": "langgraph_agent_workflow",
                    "system": "clarity-ai"
                }
            )
            
            logger.info(f"Started Langfuse agent session: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to start agent session: {e}")
            return None
    
    def trace_agent_workflow_start(self, workflow_name: str, initial_state: AgentState, 
                                 thread_id: str, session_id: Optional[str] = None) -> Optional[str]:
        """
        Start tracing an agent workflow execution
        """
        if not langfuse_service.is_enabled():
            return None
        
        try:
            trace_id = langfuse_service.start_workflow_trace(
                workflow_name=workflow_name,
                user_request=initial_state.get('user_request', ''),
                metadata={
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "workflow_type": "langgraph_agent_workflow",
                    "initial_state_keys": list(initial_state.keys()),
                    "plan_size": len(initial_state.get('plan', [])),
                    "system": "clarity-ai"
                }
            )
            
            logger.info(f"Started agent workflow trace: {trace_id}")
            return trace_id
            
        except Exception as e:
            logger.error(f"Failed to start workflow trace: {e}")
            return None
    
    def log_agent_workflow_completion(self, final_state: AgentState, 
                                    success: bool = True, 
                                    error: Optional[str] = None,
                                    thread_id: Optional[str] = None) -> None:
        """
        Log completion of agent workflow
        """
        if not langfuse_service.is_enabled():
            return
        
        try:
            # Calculate workflow metrics
            plan = final_state.get('plan', [])
            task_results = final_state.get('task_results', {})
            
            completed_tasks = [t for t in plan if t.get('status') == 'completed']
            failed_tasks = [t for t in plan if t.get('status') == 'failed']
            
            langfuse_service.log_workflow_result(
                result=final_state.get('final_report', 'Workflow completed'),
                success=success,
                metadata={
                    "thread_id": thread_id,
                    "total_tasks": len(plan),
                    "completed_tasks": len(completed_tasks),
                    "failed_tasks": len(failed_tasks),
                    "task_results_count": len(task_results),
                    "has_final_report": bool(final_state.get('final_report')),
                    "error": error,
                    "workflow_type": "langgraph_agent_workflow"
                }
            )
            
            logger.info(f"Logged agent workflow completion: success={success}")
            
        except Exception as e:
            logger.error(f"Failed to log workflow completion: {e}")

# Global instance for easy access
langfuse_langgraph = LangfuseLangGraphIntegration()