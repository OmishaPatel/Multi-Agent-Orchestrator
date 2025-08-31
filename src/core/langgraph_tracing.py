"""
LangGraph-specific tracing utilities for Langfuse integration
"""

import functools
import time
from typing import Dict, Any, Callable, Optional
from src.services.langfuse_service import langfuse_service
from src.graph.state import AgentState
import logging

logger = logging.getLogger(__name__)

def trace_langgraph_node(node_name: str):
    """
    Decorator for LangGraph nodes to automatically trace execution
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, state: AgentState) -> AgentState:
            if not langfuse_service.is_enabled():
                return func(self, state)
            
            thread_id = state.get('thread_id', 'unknown')
            start_time = time.time()
            
            # Create a simplified input state for tracing (avoid large objects)
            input_summary = {
                "user_request": state.get('user_request', '')[:100] + "..." if len(state.get('user_request', '')) > 100 else state.get('user_request', ''),
                "plan_size": len(state.get('plan', [])),
                "task_results_count": len(state.get('task_results', {})),
                "next_task_id": state.get('next_task_id'),
                "approval_status": state.get('human_approval_status'),
                "has_feedback": bool(state.get('user_feedback'))
            }
            
            try:
                # Execute the node
                result_state = func(self, state)
                execution_time = time.time() - start_time
                
                # Create output summary
                output_summary = {
                    "plan_size": len(result_state.get('plan', [])),
                    "task_results_count": len(result_state.get('task_results', {})),
                    "next_task_id": result_state.get('next_task_id'),
                    "approval_status": result_state.get('human_approval_status'),
                    "has_final_report": bool(result_state.get('final_report')),
                    "execution_time_seconds": execution_time
                }
                
                # Log node execution
                langfuse_service.log_custom_event(f"node_{node_name}", {
                    "thread_id": thread_id,
                    "node_name": node_name,
                    "execution_time": execution_time,
                    "input_summary": input_summary,
                    "output_summary": output_summary,
                    "success": True
                })
                
                logger.debug(f"Node {node_name} executed successfully in {execution_time:.2f}s")
                return result_state
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Log node error
                langfuse_service.log_custom_event(f"node_{node_name}_error", {
                    "thread_id": thread_id,
                    "node_name": node_name,
                    "execution_time": execution_time,
                    "input_summary": input_summary,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False
                })
                
                logger.error(f"Node {node_name} failed after {execution_time:.2f}s: {e}")
                raise
        
        return wrapper
    return decorator

def trace_langgraph_router(router_name: str):
    """
    Decorator for LangGraph routing functions to trace decision making
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, state: AgentState) -> str:
            if not langfuse_service.is_enabled():
                return func(self, state)
            
            thread_id = state.get('thread_id', 'unknown')
            start_time = time.time()
            
            # Create routing context
            routing_context = {
                "approval_status": state.get('human_approval_status'),
                "plan_size": len(state.get('plan', [])),
                "next_task_id": state.get('next_task_id'),
                "has_feedback": bool(state.get('user_feedback')),
                "completed_tasks": len([t for t in state.get('plan', []) if t.get('status') == 'completed'])
            }
            
            try:
                # Execute routing decision
                decision = func(self, state)
                execution_time = time.time() - start_time
                
                # Log routing decision
                langfuse_service.log_custom_event(f"router_{router_name}", {
                    "thread_id": thread_id,
                    "router_name": router_name,
                    "decision": decision,
                    "execution_time": execution_time,
                    "routing_context": routing_context,
                    "success": True
                })
                
                logger.debug(f"Router {router_name} decided: {decision} in {execution_time:.2f}s")
                return decision
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Log routing error
                langfuse_service.log_custom_event(f"router_{router_name}_error", {
                    "thread_id": thread_id,
                    "router_name": router_name,
                    "execution_time": execution_time,
                    "routing_context": routing_context,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False
                })
                
                logger.error(f"Router {router_name} failed after {execution_time:.2f}s: {e}")
                raise
        
        return wrapper
    return decorator

class LangGraphTracer:
    """
    Context manager for tracing complete LangGraph workflow execution
    """
    
    def __init__(self, workflow_name: str, thread_id: str, initial_state: AgentState):
        self.workflow_name = workflow_name
        self.thread_id = thread_id
        self.initial_state = initial_state
        self.start_time = None
        self.trace_id = None
    
    def __enter__(self):
        if not langfuse_service.is_enabled():
            return self
        
        self.start_time = time.time()
        
        # Start workflow trace
        self.trace_id = langfuse_service.trace_langgraph_workflow(
            workflow_name=self.workflow_name,
            initial_state=self.initial_state,
            thread_id=self.thread_id
        )
        
        logger.info(f"Started LangGraph workflow trace: {self.workflow_name} (thread: {self.thread_id})")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not langfuse_service.is_enabled():
            return
        
        execution_time = time.time() - self.start_time if self.start_time else 0
        success = exc_type is None
        
        # Log workflow completion
        langfuse_service.log_custom_event("workflow_complete", {
            "thread_id": self.thread_id,
            "workflow_name": self.workflow_name,
            "execution_time": execution_time,
            "success": success,
            "error": str(exc_val) if exc_val else None,
            "error_type": exc_type.__name__ if exc_type else None
        })
        
        if success:
            logger.info(f"LangGraph workflow completed successfully in {execution_time:.2f}s")
        else:
            logger.error(f"LangGraph workflow failed after {execution_time:.2f}s: {exc_val}")

def create_langgraph_config(thread_id: str, **additional_config) -> Dict[str, Any]:
    """
    Create LangGraph configuration with Langfuse integration
    """
    base_config = langfuse_service.get_langgraph_config(thread_id)
    
    # Merge additional configuration
    if additional_config:
        base_config.update(additional_config)
        if "metadata" in additional_config:
            base_config["metadata"].update(additional_config["metadata"])
    
    return base_config