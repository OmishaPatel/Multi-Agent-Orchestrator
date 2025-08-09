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
import threading

logger = get_service_logger("workflow_factory")

class WorkflowFactory:
    # Class-level storage for workflow instances (singleton pattern)
    _workflow_instances: Dict[str, StateGraph] = {}
    _instance_lock = threading.Lock()

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

    def get_or_create_workflow(self, thread_id: str) -> StateGraph:
        """
        Get existing workflow instance for thread_id or create a new one.
        This ensures the same workflow instance is used across API calls.
        """
        with self._instance_lock:
            if thread_id not in self._workflow_instances:
                logger.info(f"Creating new workflow instance for thread {thread_id}")
                workflow = self.create_workflow()
                self._workflow_instances[thread_id] = workflow
            else:
                logger.debug(f"Reusing existing workflow instance for thread {thread_id}")
            
            return self._workflow_instances[thread_id]
    
    def cleanup_workflow_instance(self, thread_id: str) -> None:
        """
        Clean up workflow instance when workflow is completed.
        This prevents memory leaks from accumulating workflow instances.
        """
        with self._instance_lock:
            if thread_id in self._workflow_instances:
                logger.info(f"Cleaning up workflow instance for thread {thread_id}")
                del self._workflow_instances[thread_id]
            else:
                logger.debug(f"No workflow instance found for cleanup: {thread_id}")

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

        # Use singleton pattern to get/create workflow instance
        workflow = self.get_or_create_workflow(thread_id)
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
            
            # SIMPLIFIED APPROACH: Just execute the planning_agent directly and manually set up the interruption state
            logger.info(f"Executing planning agent directly to generate initial plan")
            
            # Execute just the planning node to generate the plan
            planning_result = self.workflow_graph._planning_node(initial_state)
            logger.info(f"Planning completed with {len(planning_result.get('plan', []))} tasks")
            
            # Manually set up the workflow state to simulate proper interruption at await_approval
            workflow.update_state(config, planning_result)
            
            # Verify the workflow state is set up correctly
            try:
                current_workflow_state = workflow.get_state(config)
                logger.info(f"Manual workflow state setup:")
                logger.info(f"  - State values: {list(current_workflow_state.values.keys()) if current_workflow_state.values else 'None'}")
                logger.info(f"  - Next nodes: {current_workflow_state.next}")
                logger.info(f"  - Approval status: {current_workflow_state.values.get('human_approval_status', 'unknown') if current_workflow_state.values else 'unknown'}")
            except Exception as e:
                logger.warning(f"Could not verify manual workflow state: {e}")
            
            # We already have the planning_result from the direct planning execution
            logger.info(f"Initial workflow setup completed with direct planning execution")
            logger.info(f"✅ Workflow manually set up to be ready for approval/rejection")
            
            # Save state to Redis if using hybrid checkpointing
            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                logger.info(f"Saving initial workflow state to Redis")
                self.redis_state_manager.save_state(thread_id, planning_result)
            
            logger.info(f"Initial workflow setup completed with manual planning execution")
            return {"thread_id": thread_id, "result": planning_result}
        except Exception as e:
            logger.error(f"Failed to start workflow: {e}")
            raise
    

    def resume_after_approval(self, thread_id: str, approval_status: str, feedback: str = None) -> Any:
        """Resume workflow after human approval with proper state handling"""
        logger.info(f"DIAGNOSTIC: resume_after_approval called - thread_id={thread_id}, approval_status={approval_status}, feedback={feedback is not None}")
        
        # CRITICAL: Use the SAME workflow instance that was created for this thread
        workflow = self.get_or_create_workflow(thread_id)
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
                    
                    # Check workflow state - for manually set up workflows, next might be empty initially
                    if current_workflow_state.next:
                        logger.info(f"  - Workflow should resume from: {current_workflow_state.next}")
                        if "await_approval" not in current_workflow_state.next:
                            logger.info(f"  - Workflow will start from: {current_workflow_state.next}")
                    else:
                        logger.info(f"  - Workflow will start from the beginning (expected for manual setup)")
                else:
                    logger.warning(f"  - WARNING: No workflow state found - this is unexpected")
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
                # Use LangGraph's native streaming for both approved and rejected workflows
                logger.info(f"LANGGRAPH STREAMING: Using LangGraph's native streaming - approval_status={approval_status}")
                
                # CRITICAL: For approved workflows, we need to bypass the interruption and continue execution
                # Since the plan is already approved, we can continue directly to task execution
                
                if approval_status == "approved":
                    logger.info("APPROVED WORKFLOW: Creating new workflow without interruption for task execution")
                    
                    # Create a new workflow instance without interruption for task execution
                    execution_workflow = self.workflow_graph.create_workflow()
                    execution_compiled = execution_workflow.compile(checkpointer=self.checkpoint_saver)
                    
                    # Stream the execution workflow with the approved state
                    logger.info("Starting LangGraph execution streaming for approved workflow...")
                    
                    for chunk in execution_compiled.stream(complete_state, config=config, stream_mode="values"):
                        execution_count += 1
                        logger.info(f"Execution stream iteration {execution_count}")
                        
                        if execution_count > max_executions:
                            logger.warning(f"Workflow {thread_id} exceeded max executions ({max_executions}), stopping")
                            break
                        
                        if chunk:
                            result = chunk
                            
                            # Log current execution state
                            current_approval_status = result.get('human_approval_status', 'unknown')
                            plan = result.get('plan', [])
                            next_task_id = result.get('next_task_id')
                            
                            logger.info(f"  Execution chunk {execution_count}:")
                            logger.info(f"    - Approval status: {current_approval_status}")
                            logger.info(f"    - Plan tasks: {len(plan)}")
                            logger.info(f"    - Next task ID: {next_task_id}")
                            
                            # Log task statuses for debugging
                            if plan:
                                task_statuses = [task.get('status', 'unknown') for task in plan]
                                completed_count = task_statuses.count('completed')
                                in_progress_count = task_statuses.count('in_progress')
                                pending_count = task_statuses.count('pending')
                                
                                logger.info(f"    - Task statuses: {completed_count} completed, {in_progress_count} in progress, {pending_count} pending")
                                
                                # Log details of current task if any
                                if next_task_id:
                                    current_task = next((task for task in plan if task['id'] == next_task_id), None)
                                    if current_task:
                                        logger.info(f"    - Current task: {current_task.get('description', 'No description')[:50]}... [{current_task.get('status', 'unknown')}]")
                            
                            # Save state to Redis after each chunk for API access
                            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                                logger.debug(f"Saving workflow state to Redis after execution chunk {execution_count}")
                                self.redis_state_manager.save_state(thread_id, result)
                            
                            # Check for completion conditions
                            if result.get('final_report'):
                                logger.info("Workflow completed successfully - final report generated")
                                
                                # CRITICAL: Ensure complete final state preservation
                                if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                                    # Get the current workflow state to ensure we have complete data
                                    try:
                                        workflow = self.get_or_create_workflow(thread_id)
                                        config = {"configurable": {"thread_id": thread_id}}
                                        current_workflow_state = workflow.get_state(config)
                                        
                                        # Use workflow state if it has more complete data
                                        if current_workflow_state and current_workflow_state.values:
                                            workflow_state = current_workflow_state.values
                                            
                                            # Merge the final report from result into workflow state
                                            complete_final_state = workflow_state.copy()
                                            complete_final_state['final_report'] = result.get('final_report')
                                            
                                            logger.info("Saving complete final state to Redis before cleanup")
                                            logger.info(f"Complete state contains: plan={len(complete_final_state.get('plan', []))} tasks, results={len(complete_final_state.get('task_results', {}))} completed, messages={len(complete_final_state.get('messages', []))}")
                                            
                                            # Save the complete state
                                            self.redis_state_manager.save_state(thread_id, complete_final_state)
                                            
                                            # Verify the save worked
                                            verification_state = self.redis_state_manager.get_state(thread_id)
                                            if verification_state:
                                                plan_count = len(verification_state.get('plan', []))
                                                results_count = len(verification_state.get('task_results', {}))
                                                messages_count = len(verification_state.get('messages', []))
                                                logger.info(f"Final state verified in Redis: plan={plan_count} tasks, results={results_count} completed, messages={messages_count}")
                                            else:
                                                logger.warning("Final state verification failed - state not found in Redis")
                                        else:
                                            # Fallback to using result state
                                            logger.warning("Could not get workflow state, using result state as fallback")
                                            self.redis_state_manager.save_state(thread_id, result)
                                    except Exception as state_e:
                                        logger.error(f"Error preserving complete final state: {state_e}")
                                        # Fallback to saving result state
                                        self.redis_state_manager.save_state(thread_id, result)
                                
                                # Clean up workflow instance to prevent memory leaks
                                self.cleanup_workflow_instance(thread_id)
                                break
                            elif plan and all(task.get('status') == 'completed' for task in plan):
                                logger.info("All tasks completed - workflow should finish soon")
                                # Continue streaming to let compile_results run
                
                else:
                    # For rejected workflows, use the original interrupted workflow
                    logger.info("REJECTED WORKFLOW: Using interrupted workflow for plan regeneration")
                    
                    for chunk in workflow.stream(None, config=config, stream_mode="values"):
                        execution_count += 1
                        logger.info(f"Rejection stream iteration {execution_count}")
                        
                        if execution_count > max_executions:
                            logger.warning(f"Workflow {thread_id} exceeded max executions ({max_executions}), stopping")
                            break
                        
                        if chunk:
                            result = chunk
                            
                            # Log current execution state
                            current_approval_status = result.get('human_approval_status', 'unknown')
                            plan = result.get('plan', [])
                            
                            logger.info(f"  Rejection chunk {execution_count}:")
                            logger.info(f"    - Approval status: {current_approval_status}")
                            logger.info(f"    - Plan tasks: {len(plan)}")
                            
                            # Save state to Redis after each chunk for API access
                            if self.checkpointing_type == "hybrid" and self.redis_state_manager:
                                logger.debug(f"Saving workflow state to Redis after rejection chunk {execution_count}")
                                self.redis_state_manager.save_state(thread_id, result)
                            
                            # Check for completion conditions
                            if current_approval_status == 'pending':
                                logger.info("Plan regenerated successfully for rejected workflow")
                                break
                
                logger.info(f"LangGraph streaming completed after {execution_count} iterations")
                
                # Final state is already saved to Redis during streaming
                # Log final execution summary
                if result:
                    plan = result.get('plan', [])
                    task_results = result.get('task_results', {})
                    final_report = result.get('final_report')
                    
                    logger.info(f"Workflow execution completed:")
                    logger.info(f"  - Plan: {len(plan)} tasks")
                    logger.info(f"  - Task results: {len(task_results)} completed")
                    logger.info(f"  - Final report: {'Generated' if final_report else 'Not generated'}")
                    
                    # Log task completion summary
                    if plan:
                        completed_tasks = [t for t in plan if t.get('status') == 'completed']
                        failed_tasks = [t for t in plan if t.get('status') == 'failed']
                        logger.info(f"  - Completed tasks: {len(completed_tasks)}/{len(plan)}")
                        if failed_tasks:
                            logger.warning(f"  - Failed tasks: {len(failed_tasks)}")
                else:
                    logger.warning("No final result available from workflow execution")
                
                return result
                
            except Exception as stream_e:
                logger.error(f"LangGraph streaming failed: {stream_e}, trying invoke as fallback")
                
                # Fallback to invoke (should rarely be needed with singleton pattern)
                try:
                    result = workflow.invoke(None, config=config)
                    
                    # Save fallback result to Redis
                    if result and self.checkpointing_type == "hybrid" and self.redis_state_manager:
                        logger.info(f"Saving fallback invoke result to Redis")
                        self.redis_state_manager.save_state(thread_id, result)
                    
                    return result
                except Exception as invoke_e:
                    logger.error(f"Both streaming and invoke failed: {invoke_e}")
                    raise stream_e  # Raise the original streaming error
                
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
                
                # Also try to get current workflow state for comparison (only if workflow instance exists)
                workflow_state = None
                try:
                    # Check if workflow instance exists before trying to access it
                    with self._instance_lock:
                        if thread_id in self._workflow_instances:
                            workflow = self._workflow_instances[thread_id]
                            config = {"configurable": {"thread_id": thread_id}}
                            current_state = workflow.get_state(config)
                            if current_state and current_state.values:
                                workflow_state = current_state.values
                        else:
                            logger.debug(f"Workflow instance for {thread_id} has been cleaned up, using Redis state only")
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
                    # Use singleton pattern to get the same workflow instance
                    workflow = self.get_or_create_workflow(thread_id)
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

