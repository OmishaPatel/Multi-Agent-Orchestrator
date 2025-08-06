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
            # Create properly initialized initial state
            initial_state = {
                "user_request": user_request,
                "plan": [],
                "task_results": {},
                "next_task_id": None,
                "messages": [],  # Initialize messages as empty list
                "human_approval_status": "pending",
                "user_feedback": None,
                "final_report": None
            }
            
            result = workflow.invoke(initial_state, config=config)
            
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
        logger.info(f"DIAGNOSTIC: resume_after_approval called - thread_id={thread_id}, approval_status={approval_status}, feedback={feedback is not None}")
        
        workflow = self.create_workflow()
        config = {"configurable": {"thread_id": thread_id}}
        
        # CRITICAL: For hybrid checkpointing, we need to ensure the LangGraph state
        # is synchronized with our Redis state since we're creating a new workflow instance
        
        try:
            # CRITICAL: Get the most recent state from Redis first (this is our source of truth)
            authoritative_state = None
            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                redis_state = self.redis_state_manager.get_state(thread_id)
                if redis_state:
                    authoritative_state = redis_state
                    logger.info(f"Using Redis state as authoritative source")
                    logger.info(f"Redis state has {len(redis_state.get('plan', []))} tasks")
                    
                    # Log the plan details to verify we have the right state
                    for i, task in enumerate(redis_state.get('plan', [])):
                        logger.info(f"  Redis Task {task.get('id', i)}: {task.get('description', 'No description')[:60]}...")
            
            # Fallback: try to get current workflow state
            if not authoritative_state:
                try:
                    current_workflow_state = workflow.get_state(config)
                    if current_workflow_state and current_workflow_state.values:
                        authoritative_state = current_workflow_state.values
                        logger.info(f"Using workflow state as fallback")
                        logger.info(f"Workflow state has {len(authoritative_state.get('plan', []))} tasks")
                except Exception as e:
                    logger.warning(f"Could not get current workflow state: {e}")
            
            # If we still don't have a proper state, something is wrong
            if not authoritative_state:
                logger.error(f"No valid state found for workflow {thread_id}")
                raise ValueError(f"Cannot resume workflow {thread_id}: no valid state found")
            
            # Create the complete state update with approval decision
            complete_state = {
                "user_request": authoritative_state.get("user_request", ""),
                "plan": authoritative_state.get("plan", []),
                "task_results": authoritative_state.get("task_results", {}),
                "next_task_id": authoritative_state.get("next_task_id"),
                "messages": authoritative_state.get("messages", []),
                "human_approval_status": approval_status,
                "user_feedback": feedback if approval_status == "rejected" else None,
                "final_report": authoritative_state.get("final_report")
            }
            
            logger.info(f"Updating workflow with complete state:")
            logger.info(f"  - Approval status: {approval_status}")
            logger.info(f"  - Plan tasks: {len(complete_state['plan'])}")
            logger.info(f"  - Messages: {len(complete_state['messages'])}")
            logger.info(f"  - Has feedback: {feedback is not None}")
            
            # Log the plan we're preserving
            for i, task in enumerate(complete_state['plan']):
                logger.info(f"  Preserving Task {task.get('id', i)}: {task.get('description', 'No description')[:60]}...")
            
            # Update the workflow state with the complete state
            workflow.update_state(config, complete_state)
            
            # Continue workflow
            logger.info(f"Resuming {self.checkpointing_type}-checkpointed workflow {thread_id} after approval")
            
            # CRITICAL DEBUG: Check the current workflow state before resuming
            try:
                current_workflow_state = workflow.get_state(config)
                if current_workflow_state:
                    logger.info(f"BEFORE RESUME - Current workflow state:")
                    logger.info(f"  - Next nodes: {current_workflow_state.next}")
                    logger.info(f"  - Values keys: {list(current_workflow_state.values.keys()) if current_workflow_state.values else 'None'}")
                    if current_workflow_state.values:
                        logger.info(f"  - Approval status in state: {current_workflow_state.values.get('human_approval_status', 'unknown')}")
                        logger.info(f"  - Plan tasks in state: {len(current_workflow_state.values.get('plan', []))}")
            except Exception as debug_e:
                logger.warning(f"Could not get workflow state for debugging: {debug_e}")
            
            # If approved, we should proceed to task execution, not regenerate plan
            if approval_status == "approved":
                logger.info("Plan approved - workflow should proceed to task execution")
                # Save the current state to Redis before continuing
                if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                    logger.info("Saving approved state to Redis before task execution")
                    self.redis_state_manager.save_state(thread_id, complete_state)
                
                # CRITICAL: For approved plans, we need to force the workflow to continue
                # The workflow is paused at await_approval, so we need to resume it properly
                logger.info("Forcing workflow continuation for approved plan")
                
                # Try to manually trigger the next steps in the workflow
                try:
                    # Get the current workflow state to see where we are
                    current_workflow_state = workflow.get_state(config)
                    if current_workflow_state:
                        logger.info(f"Current workflow state: next={current_workflow_state.next}")
                        logger.info(f"Current workflow values keys: {list(current_workflow_state.values.keys()) if current_workflow_state.values else 'None'}")
                except Exception as state_e:
                    logger.warning(f"Could not get current workflow state: {state_e}")
            
            result = None
            execution_count = 0
            max_executions = 25  # Increased for approved plans that need to execute tasks
            
            try:
                # For approved plans, we need to continue the workflow to reach task execution
                should_continue = True
                
                # Special handling for approved plans - they should continue to task execution
                if approval_status == "approved":
                    logger.info("Starting task execution for approved plan")
                    # The workflow should continue from await_approval -> task_selector -> task execution
                    # We've already updated the state with approval_status="approved"
                
                # For approved plans, we need to continue from the await_approval state, not restart
                # The workflow is paused at await_approval, so we should resume from there
                # For rejected plans, we pass None to restart from planning_agent
                # CRITICAL: For interrupted workflows, we must pass None to continue from interruption point
                stream_input = None
                
                # For interrupted workflows, we need to continue from where they left off
                # The workflow is paused at await_approval, so we resume with None input
                for chunk in workflow.stream(stream_input, config=config, stream_mode="values"):
                    execution_count += 1
                    logger.info(f"Workflow stream iteration {execution_count}, chunk: {list(chunk.keys()) if chunk else 'None'}")
                    
                    if execution_count > max_executions:
                        logger.warning(f"Workflow {thread_id} exceeded max executions ({max_executions}), stopping")
                        break
                        
                    if chunk:
                        result = chunk
                        # Log progress for debugging
                        for node_name, node_result in chunk.items():
                            logger.info(f"Executed node {node_name} (execution {execution_count})")
                            if node_result and isinstance(node_result, dict):
                                approval_status_result = node_result.get('human_approval_status', 'unknown')
                                plan_count = len(node_result.get('plan', []))
                                next_task_id = node_result.get('next_task_id')
                                logger.info(f"  - Approval status: {approval_status_result}")
                                logger.info(f"  - Plan tasks: {plan_count}")
                                logger.info(f"  - Next task ID: {next_task_id}")
                                
                                # Log the first task to verify we have the right plan
                                if node_result.get('plan') and len(node_result['plan']) > 0:
                                    first_task = node_result['plan'][0]
                                    logger.info(f"  - First task: {first_task.get('description', 'No description')[:60]}...")
                                    logger.info(f"  - First task status: {first_task.get('status', 'unknown')}")
                                
                                # Save state after each node execution
                                if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                                    logger.info(f"Saving state after {node_name} execution")
                                    self.redis_state_manager.save_state(thread_id, node_result)
                                
                                # If we're back to pending approval (plan regeneration), save state and break
                                if approval_status_result == 'pending' and plan_count > 0 and approval_status == "rejected":
                                    logger.info(f"Plan regenerated successfully, stopping execution")
                                    should_continue = False
                                    break
                                
                                # For approved plans, continue execution until tasks actually start
                                if approval_status == "approved":
                                    # Check if any tasks are now in progress or completed
                                    task_statuses = [task.get('status', 'pending') for task in node_result.get('plan', [])]
                                    
                                    if any(status in ['in_progress', 'completed'] for status in task_statuses):
                                        logger.info(f"Tasks are now executing! Found task statuses: {task_statuses}")
                                        # Continue for a few more steps to let tasks complete
                                        if execution_count >= 20:  # Allow even more time for task completion
                                            logger.info(f"Tasks executing, stopping after {execution_count} steps")
                                            should_continue = False
                                            break
                                    else:
                                        # For approved plans, be very aggressive about continuing
                                        logger.info(f"Approved plan - continuing execution (step {execution_count})")
                                        logger.info(f"Current node: {node_name}, task statuses: {task_statuses}")
                                        
                                        # Only stop if we've really tried many times
                                        if execution_count >= 25:  # Much higher limit
                                            logger.warning(f"Approved plan execution stopping after {execution_count} steps - may need investigation")
                                            should_continue = False
                                            break
                        
                        if not should_continue:
                            break
                
                # Save final state to Redis if using hybrid checkpointing
                if result and self.checkpointing_type == "hybrid" and self.redis_state_manager:
                    # The result from workflow.stream() is the actual state, not a node result
                    final_state = None
                    
                    # Check if result is the state itself (AddableValuesDict or similar)
                    if hasattr(result, 'get') and 'plan' in result:
                        final_state = dict(result)  # Convert to regular dict
                        logger.info(f"Using workflow stream result as final state")
                    elif isinstance(result, dict) and 'plan' in result:
                        final_state = result
                        logger.info(f"Using result dict as final state")
                    else:
                        # Fallback: try to extract from node results
                        if isinstance(result, dict):
                            for node_name, node_result in result.items():
                                if isinstance(node_result, dict) and 'plan' in node_result:
                                    final_state = node_result
                                    logger.info(f"Extracted final state from node '{node_name}'")
                                    break
                    
                    if final_state:
                        logger.info(f"Saving final state to Redis: approval_status={final_state.get('human_approval_status')}, plan_tasks={len(final_state.get('plan', []))}")
                        # Log the plan details for debugging
                        plan = final_state.get('plan', [])
                        for i, task in enumerate(plan):
                            task_status = task.get('status', 'unknown')
                            logger.info(f"  Saving task {task.get('id', i+1)}: {task.get('description', 'No description')[:50]}... [{task_status}]")
                        
                        # Log final report status
                        final_report = final_state.get('final_report')
                        logger.info(f"  Final report: {'Generated' if final_report else 'Not generated'}")
                        
                        self.redis_state_manager.save_state(thread_id, final_state)
                        logger.info(f"Successfully saved final state to Redis")
                    else:
                        logger.warning(f"Could not extract final state from result for Redis save")
                        logger.info(f"Result type: {type(result)}, keys: {list(result.keys()) if hasattr(result, 'keys') else 'No keys'}")
                        # Try to get current state and save that
                        try:
                            current_state = workflow.get_state(config)
                            if current_state and current_state.values:
                                logger.info(f"Saving current workflow state as fallback")
                                self.redis_state_manager.save_state(thread_id, current_state.values)
                        except Exception as fallback_e:
                            logger.error(f"Failed to save fallback state: {fallback_e}")
                
                logger.info(f"DIAGNOSTIC: Workflow stream completed after {execution_count} iterations")
                logger.info(f"DIAGNOSTIC: Final result type: {type(result)}")
                
                if result and isinstance(result, dict):
                    # Check if this is a node result or final state
                    if len(result) == 1 and list(result.keys())[0] in ['planning_agent', 'task_selector', 'research_agent', 'code_agent', 'compile_results']:
                        # This is a single node result, extract the actual state
                        node_name = list(result.keys())[0]
                        actual_result = result[node_name]
                        logger.info(f"DIAGNOSTIC: Extracted result from node '{node_name}'")
                        result = actual_result
                    
                    plan = result.get('plan', [])
                    task_results = result.get('task_results', {})
                    final_report = result.get('final_report')
                    
                    logger.info(f"DIAGNOSTIC: Final state - Plan: {len(plan)} tasks, Task results: {len(task_results)}, Final report: {'Yes' if final_report else 'No'}")
                    
                    # Log task statuses
                    for i, task in enumerate(plan):
                        status = task.get('status', 'unknown')
                        logger.info(f"DIAGNOSTIC: Final Task {i+1} status: {status}")
                
                return result
                
            except Exception as stream_e:
                logger.warning(f"Stream approach failed: {stream_e}, trying invoke")
                # Fallback to invoke
                result = workflow.invoke(None, config=config)
                
                # Save final state to Redis if using hybrid checkpointing
                if result and self.checkpointing_type == "hybrid" and self.redis_state_manager:
                    logger.info(f"Saving invoke result to Redis: approval_status={result.get('human_approval_status')}, plan_tasks={len(result.get('plan', []))}")
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
                        
                        # Save current state to Redis for status retrieval
                        if (self.checkpointing_type == "hybrid" and 
                            self.redis_state_manager and current_state.values):
                            self.redis_state_manager.save_state(thread_id, current_state.values)
                            
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
                # Hybrid checkpointing - get state from Redis first
                redis_state = self.redis_state_manager.get_state(thread_id)
                
                # Also try to get current workflow state for comparison
                workflow_state = None
                try:
                    workflow = self.create_workflow()
                    config = {"configurable": {"thread_id": thread_id}}
                    current_state = workflow.get_state(config)
                    if current_state and current_state.values:
                        workflow_state = current_state.values
                except Exception as e:
                    logger.debug(f"Could not get workflow state for {thread_id}: {e}")
                
                # Use the most complete state available
                if redis_state and workflow_state:
                    # Compare and use the one with more complete data
                    redis_plan_count = len(redis_state.get('plan', []))
                    workflow_plan_count = len(workflow_state.get('plan', []))
                    
                    if workflow_plan_count > redis_plan_count:
                        logger.info(f"Using workflow state (has {workflow_plan_count} tasks vs Redis {redis_plan_count})")
                        state = workflow_state
                    else:
                        logger.info(f"Using Redis state (has {redis_plan_count} tasks vs workflow {workflow_plan_count})")
                        state = redis_state
                elif redis_state:
                    state = redis_state
                elif workflow_state:
                    state = workflow_state
                else:
                    logger.warning(f"No state found for workflow {thread_id}")
                    return {
                        "thread_id": thread_id, 
                        "status": "not_found",
                        "checkpointing": self.checkpointing_type
                    }
                
                return {
                    "thread_id": thread_id,
                    "user_request": state.get("user_request", ""),
                    "plan": state.get("plan", []),
                    "task_results": state.get("task_results", {}),
                    "next_task_id": state.get("next_task_id"),
                    "messages": state.get("messages", []),
                    "human_approval_status": state.get("human_approval_status", "pending"),
                    "user_feedback": state.get("user_feedback"),
                    "final_report": state.get("final_report"),
                    "checkpointing": self.checkpointing_type
                }
            elif self.checkpointing_enabled:
                # Memory checkpointing - try to get current state
                try:
                    workflow = self.create_workflow()
                    config = {"configurable": {"thread_id": thread_id}}
                    current_state = workflow.get_state(config)
                    if current_state and current_state.values:
                        state = current_state.values
                        return {
                            "thread_id": thread_id,
                            "user_request": state.get("user_request", ""),
                            "plan": state.get("plan", []),
                            "task_results": state.get("task_results", {}),
                            "next_task_id": state.get("next_task_id"),
                            "messages": state.get("messages", []),
                            "human_approval_status": state.get("human_approval_status", "pending"),
                            "user_feedback": state.get("user_feedback"),
                            "final_report": state.get("final_report"),
                            "checkpointing": self.checkpointing_type
                        }
                except Exception as e:
                    logger.debug(f"Could not get memory state: {e}")
                
                # Fallback for memory checkpointing
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

