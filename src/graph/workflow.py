from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END
from src.graph.state import AgentState, SubTask, TaskType, TaskStatus, ApprovalStatus, TimestampUtils
from src.agents.planning_agent import PlanningAgent
from src.agents.research_agent import ResearchAgent
from src.agents.code_agent import CodeAgent
from src.utils.logging_config import get_logger, get_workflow_logger, log_state_transition
from src.core.redis_state_manager import RedisStateManager
from src.services.langfuse_service import langfuse_service
from src.core.langgraph_tracing import trace_langgraph_node, trace_langgraph_router, LangGraphTracer
from src.core.langfuse_langgraph_integration import langfuse_langgraph

logger = get_workflow_logger()

class IntelligentWorkflowGraph:   
    def __init__(self):
        try:
            logger.info("Initializing workflow graph agents...")
            logger.info("Creating planning agent...")
            self.planning_agent = PlanningAgent()
            logger.info("Planning agent created successfully")
            
            logger.info("Creating research agent...")
            self.research_agent = ResearchAgent()
            logger.info("Research agent created successfully")
            
            logger.info("Creating code agent...")
            self.code_agent = CodeAgent()
            logger.info("Code agent created successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize workflow graph agents: {e}", exc_info=True)
            raise


    def run_workflow(self, initial_state: AgentState, user_id: str = None) -> Dict[str, Any]:
        """
        Main workflow execution with native LangGraph + Langfuse integration
        This enables agent graph visualization in Langfuse dashboard
        """
        thread_id = initial_state.get('thread_id', 'unknown')
        user_id = user_id or initial_state.get('user_id', 'anonymous')
        
        # Start Langfuse agent session
        session_id = langfuse_langgraph.start_agent_session(
            user_id=user_id,
            initial_request=initial_state.get('user_request', ''),
            thread_id=thread_id
        )
        
        # Start workflow trace
        trace_id = langfuse_langgraph.trace_agent_workflow_start(
            workflow_name="clarity_ai_agent_workflow",
            initial_state=initial_state,
            thread_id=thread_id,
            session_id=session_id
        )
        
        try:
            # Create workflow with native Langfuse integration
            workflow = self.create_workflow()
            
            # Create traced workflow for agent graph visualization
            compiled_workflow = langfuse_langgraph.create_traced_workflow(
                workflow=workflow,
                thread_id=thread_id,
                user_id=user_id,
                session_id=session_id
            )
            
            # Set up checkpointer if available
            if RedisStateManager().is_enabled():
                # Re-compile with checkpointer
                compiled_workflow = workflow.compile(
                    checkpointer=RedisStateManager().get_checkpointer(),
                    interrupt_before=["await_approval"]
                )
            
            # Get execution config with Langfuse integration
            config = langfuse_langgraph.get_execution_config(
                thread_id=thread_id,
                user_id=user_id,
                session_id=session_id
            )
            
            # Execute the workflow - this will create agent graph in Langfuse
            try:
                result = compiled_workflow.invoke(initial_state, config=config)
                
                # Log successful completion
                langfuse_langgraph.log_agent_workflow_completion(
                    final_state=result,
                    success=True,
                    thread_id=thread_id
                )
            
                return result

            except Exception as execution_error:
                logger.error(f"LangGraph execution failed: {execution_error}")
                
                # Log workflow failure
                if langfuse_service.is_enabled():
                    langfuse_langgraph.log_agent_workflow_completion(
                        final_state=initial_state,
                        success=False,
                        error=str(execution_error),
                        thread_id=thread_id
                    )
                raise

            
                
        except Exception as e:
            logger.error(f"Workflow setup failed: {e}")
            raise


    def _save_intermediate_state(self, state: AgentState, context: str = "") -> None:
        try:
            thread_id = state.get('thread_id', 'unknown')
            from src.core.redis_state_manager import RedisStateManager
            redis_manager = RedisStateManager()
            if redis_manager:
                redis_manager.save_state(thread_id, state)
                logger.debug(f"Saved intermediate state: {context}")
        except Exception as e:
            logger.warning(f"Failed to save intermediate state ({context}): {e}")

    def create_workflow(self) -> StateGraph:
        """Create the main workflow graph with intelligent routing"""
        
        # Create the state graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("planning_agent", self._planning_node)
        workflow.add_node("await_approval", self._await_approval_node)
        workflow.add_node("task_selector", self._task_selector_node)
        workflow.add_node("research_agent", self._research_node)
        workflow.add_node("code_agent", self._code_node)
        workflow.add_node("compile_results", self._compile_results_node)
        
        # Set entry point
        workflow.set_entry_point("planning_agent")
        
        # Add edges with intelligent routing
        workflow.add_edge("planning_agent", "await_approval")
        
        # Conditional routing after approval
        workflow.add_conditional_edges(
            "await_approval",
            self._approval_router,
            {
                "approved": "task_selector",
                "rejected": "planning_agent", 
                "end": END
            }
        )
        
        # Intelligent task routing
        workflow.add_conditional_edges(
            "task_selector",
            self._intelligent_task_router,
            {
                "research": "research_agent",
                "code": "code_agent",
                "complete": "compile_results",
                "end": END
            }
        )
        
        # Return to task selector after agent execution
        workflow.add_edge("research_agent", "task_selector")
        workflow.add_edge("code_agent", "task_selector")
        
        # End workflow after compilation
        workflow.add_edge("compile_results", END)
        
        logger.info("Created intelligent workflow graph with conditional routing")
        return workflow
    
    @trace_langgraph_node("planning")
    def _planning_node(self, state: AgentState) -> AgentState:
        """Planning agent node - decomposes user request into structured tasks"""
        thread_id = state.get('thread_id', 'unknown')
        log_state_transition("start", "planning", thread_id)
            # Add LangFuse tracing
        with langfuse_service.trace_agent_execution(
            agent_name="planning",
            task_description=f"Generate plan for: {state.get('user_request', '')[:100]}...",
            metadata={
                "thread_id": thread_id,
                "approval_status": state.get('human_approval_status', 'pending'),
                "existing_plan_size": len(state.get('plan', []))
            }
        ) as span:
            try:
                # CRITICAL: Check if we already have an approved plan - don't regenerate!
                current_approval_status = state.get('human_approval_status', 'pending')
                existing_plan = state.get('plan', [])
                
                if current_approval_status == 'approved' and existing_plan:
                    logger.info(f"Plan already approved with {len(existing_plan)} tasks - skipping regeneration")
                    logger.info("Proceeding directly to task execution")
                    # Create new state that preserves the approved plan but allows workflow to continue
                    new_state = state.copy()
                    # Keep the approved plan and status - the workflow should continue to await_approval
                    new_state['human_approval_status'] = ApprovalStatus.APPROVED  # Keep it approved
                    # Set the next task for execution
                    new_state['next_task_id'] = self._get_next_executable_task_id(new_state)
                    logger.info(f"Set next_task_id to: {new_state['next_task_id']} for approved plan")
                    
                    # Ensure messages are preserved
                    if 'messages' not in new_state or new_state['messages'] is None:
                        new_state['messages'] = []
                    
                    # The workflow should continue to await_approval node, which will route to task_selector
                    log_state_transition("planning", "await_approval", thread_id)
                    # Plan reused - events are logged automatically by context manager
                    
                    langfuse_service.log_custom_event("plan_reused", {
                        "thread_id": thread_id,
                        "plan_size": len(existing_plan)
                    })
                    logger.info("Approved plan will continue to await_approval -> task_selector -> task execution")
                    return new_state
                
                # Generate or regenerate plan based on feedback
                if state.get('human_approval_status') == 'rejected' and state.get('user_feedback'):
                    logger.info(f"Regenerating plan based on user feedback: {state.get('user_feedback')}")
                    plan = self.planning_agent.regenerate_plan(
                        state['user_request'], 
                        state['user_feedback'],
                        state.get('plan', [])
                    )
                    action = "plan_regenerated"
                    logger.info(f"Plan regeneration completed with {len(plan)} tasks")
                else:
                    logger.info("Generating initial plan")
                    plan = self.planning_agent.generate_plan(state['user_request'])
                    action = "plan_generated"
                    logger.info(f"Initial plan generation completed with {len(plan)} tasks")
                
                # Log successful planning to LangFuse - no need to update span since we use events
                
                langfuse_service.log_custom_event(action, {
                    "thread_id": thread_id,
                    "plan_size": len(plan),
                    "task_types": [task.get('type') for task in plan],
                    "user_feedback": state.get('user_feedback') if action == "plan_regenerated" else None
                })
                # Update state with new plan
                new_state = state.copy()
                new_state['plan'] = plan
                new_state['human_approval_status'] = ApprovalStatus.PENDING  # Use constant instead of string
                new_state['user_feedback'] = None  # Clear feedback after processing
                
                # Reset task results for new plan
                new_state['task_results'] = {}
                
                # Set first task as next
                if plan:
                    new_state['next_task_id'] = self._get_next_executable_task_id(new_state)
                    logger.info(f"Set next_task_id to: {new_state['next_task_id']}")
                else:
                    new_state['next_task_id'] = None
                
                # Add message to indicate plan regeneration
                if 'messages' not in new_state or new_state['messages'] is None:
                    new_state['messages'] = []
                    
                if state.get('human_approval_status') == 'rejected':
                    new_state['messages'].append("Plan regenerated based on user feedback")
                    logger.info("Added regeneration message to state")
                else:
                    new_state['messages'].append("Initial plan generated")
                    logger.info("Added initial plan message to state")
                
                log_state_transition("planning", "await_approval", thread_id)
                logger.info(f"Planning node completed: {len(plan)} tasks, approval status: {new_state['human_approval_status']}")
                
                # Log the plan details for debugging
                for i, task in enumerate(plan):
                    logger.info(f"  Task {task['id']}: {task['description']} [{task['type']}]")
                
                # CRITICAL: Force save state to Redis after plan generation/regeneration
                # This ensures the revised plan is immediately persisted
                try:
                    from src.core.redis_state_manager import RedisStateManager
                    redis_manager = RedisStateManager()
                    if redis_manager:
                        logger.info("Force-saving planning state to Redis")
                        redis_manager.save_state(thread_id, new_state)
                        logger.info("Planning state saved to Redis successfully")
                except Exception as redis_e:
                    logger.warning(f"Failed to force-save planning state to Redis: {redis_e}")
                
                return new_state
            
            except Exception as e:
                 # Log error to LangFuse - no need to update span since we use events
                
                langfuse_service.log_custom_event("planning_error", {
                    "thread_id": thread_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                logger.error(f"Planning agent failed: {e}", exc_info=True)
                # Return state with error indication but preserve original state structure
                error_state = state.copy()
                error_state['plan'] = []
                error_state['human_approval_status'] = ApprovalStatus.PENDING
                error_state['user_feedback'] = None
                error_state['next_task_id'] = None
                
                if 'messages' not in error_state or error_state['messages'] is None:
                    error_state['messages'] = []
                error_state['messages'].append(f"Planning failed: {str(e)}")
                
                return error_state
    
    @trace_langgraph_node("await_approval")
    def _await_approval_node(self, state: AgentState) -> AgentState:
        """Await approval node - pauses execution for human review"""
        logger.info("Awaiting human approval for plan")
        
        # This node simply returns the state unchanged
        # The workflow will pause here due to interrupt_before configuration
        return state
    
    @trace_langgraph_node("task_selector")
    def _task_selector_node(self, state: AgentState) -> AgentState:
        """Task selector node - determines next task and prepares for execution"""
        logger.info("Selecting next task for execution")
        
        try:
            # Log current state for debugging
            logger.info(f"Current plan has {len(state.get('plan', []))} tasks")
            for task in state.get('plan', []):
                logger.info(f"  Task {task['id']}: {task['description']} [{task['status']}]")
            
            # Get next executable task
            next_task_id = self._get_next_executable_task_id(state)
            
            if next_task_id is None:
                logger.info("No more executable tasks found")
                new_state = state.copy()
                new_state['next_task_id'] = None
                return new_state
            
            # Update task status to in_progress
            new_state = state.copy()
            new_state['next_task_id'] = next_task_id
            
            # Update task status
            for task in new_state['plan']:
                if task['id'] == next_task_id:
                    TimestampUtils.set_task_started(task)
                    logger.info(f"Selected task {next_task_id}: {task['description']}")
                    break
            self._save_intermediate_state(new_state, f"task {next_task_id} started")
            return new_state
            
        except Exception as e:
            logger.error(f"Task selector failed: {e}", exc_info=True)
            return state
    
    @trace_langgraph_node("research")
    def _research_node(self, state: AgentState) -> AgentState:
        """Research agent node - handles research and analysis tasks"""
        thread_id = state.get('thread_id', 'unknown')
        log_state_transition("task_selection", "research_execution", thread_id)
        
        # Get current task first
        current_task = self._get_current_task(state)
        if not current_task:
            logger.warning("No current task found for research agent")
            return state

        # Add LangFuse tracing
        with langfuse_service.trace_agent_execution(
            agent_name="research",
            task_description=current_task.get('description', ''),
            metadata={
                "thread_id": thread_id,
                "task_id": current_task.get('id'),
                "task_type": current_task.get('type'),
                "dependencies": current_task.get('dependencies', [])
            }
        ) as span:
        
            try:
                
                # Execute research task
                result = self.research_agent.execute_task(
                    current_task['description'],
                    context=state.get('task_results', {})
                )
                
                # Update state with results
                new_state = state.copy()
                if new_state.get('task_results') is None:
                    new_state['task_results'] = {}
                new_state['task_results'][current_task['id']] = result
                
                # Update task status
                for task in new_state['plan']:
                    if task['id'] == current_task['id']:
                        TimestampUtils.set_task_completed(task, result)
                        break
            # Log successful completion to LangFuse - events are logged automatically by context manager
                
                langfuse_service.log_custom_event("task_completed", {
                    "thread_id": thread_id,
                    "task_id": current_task['id'],
                    "task_type": "research",
                    "result_length": len(str(result))
                })
            
                self._save_intermediate_state(new_state, f"research task {current_task['id']} completed")
                log_state_transition("research_execution", "task_completed", thread_id)
                logger.info(f"Completed research task {current_task['id']}")
                return new_state
                
            except Exception as e:
                # Error logged automatically by context manager
                
                langfuse_service.log_custom_event("task_error", {
                    "thread_id": thread_id,
                    "task_id": current_task.get('id'),
                    "task_type": "research",
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                logger.error(f"Research agent failed: {e}", exc_info=True)
                # Mark task as failed
                return self._mark_task_failed(state, str(e))
    
    @trace_langgraph_node("code")
    def _code_node(self, state: AgentState) -> AgentState:
        """Code agent node - handles coding and computational tasks"""
        thread_id = state.get('thread_id', 'unknown')
        log_state_transition("task_selection", "code_execution", thread_id)

        # Get current task first
        current_task = self._get_current_task(state)
        if not current_task:
            logger.warning("No current task found for code agent")
            return state

        # Add LangFuse tracing
        with langfuse_service.trace_agent_execution(
            agent_name="code",
            task_description=current_task.get('description', ''),
            metadata={
                "thread_id": thread_id,
                "task_id": current_task.get('id'),
                "task_type": current_task.get('type'),
                "dependencies": current_task.get('dependencies', [])
            }
        ) as span:
        
            try:
                # Execute code task
                result = self.code_agent.execute_task(
                    current_task['description'],
                    context=state.get('task_results', {})
                )
                
                # Update state with results
                new_state = state.copy()
                if new_state.get('task_results') is None:
                    new_state['task_results'] = {}
                new_state['task_results'][current_task['id']] = result
                
                # Update task status
                for task in new_state['plan']:
                    if task['id'] == current_task['id']:
                        TimestampUtils.set_task_completed(task, result)
                        break
            # Log successful completion to LangFuse - events are logged automatically by context manager
                
                langfuse_service.log_custom_event("task_completed", {
                    "thread_id": thread_id,
                    "task_id": current_task['id'],
                    "task_type": "code",
                    "result_length": len(str(result))
                })
            
                self._save_intermediate_state(new_state, f"code task {current_task['id']} completed")
                log_state_transition("code_execution", "task_completed", thread_id)
                logger.info(f"Completed code task {current_task['id']}")
                return new_state
                
            except Exception as e:
                # Log error to LangFuse - error logged automatically by context manager
                
                langfuse_service.log_custom_event("task_error", {
                    "thread_id": thread_id,
                    "task_id": current_task.get('id'),
                    "task_type": "code",
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                logger.error(f"Code agent failed: {e}", exc_info=True)
                # Mark task as failed
                return self._mark_task_failed(state, str(e))
    
    @trace_langgraph_node("compile_results")
    def _compile_results_node(self, state: AgentState) -> AgentState:
        """Compile results node - creates final report from all task results"""
        logger.info("Compiling final results")
        
        try:
            # Generate final report
            final_report = self._generate_final_report(state)
            
            new_state = state.copy()
            new_state['final_report'] = final_report
            
            logger.info("Final report compiled successfully")
            return new_state
            
        except Exception as e:
            logger.error(f"Result compilation failed: {e}", exc_info=True)
            error_state = state.copy()
            error_state['final_report'] = f"Error compiling results: {str(e)}"
            return error_state
    
    @trace_langgraph_router("approval")
    def _approval_router(self, state: AgentState) -> str:
        """Route based on human approval status"""
        approval_status = state.get('human_approval_status', 'pending')
        user_feedback = state.get('user_feedback')
        thread_id = state.get('thread_id', 'unknown')
        
        logger.info(f"Approval router called with status: {approval_status}")
        # Log routing decision to LangFuse
        langfuse_service.log_custom_event("approval_routing", {
            "thread_id": thread_id,
            "approval_status": approval_status,
            "has_feedback": bool(user_feedback),
            "plan_size": len(state.get('plan', []))
        })
        logger.info(f"User feedback: {user_feedback}")
        logger.info(f"State keys: {list(state.keys())}")
        logger.info(f"Plan has {len(state.get('plan', []))} tasks")
        
        # Log the current plan to verify we have the right one
        if state.get('plan') and len(state['plan']) > 0:
            first_task = state['plan'][0]
            logger.info(f"Current plan first task: {first_task.get('description', 'No description')[:60]}...")
            
            # Log all tasks for debugging
            for i, task in enumerate(state['plan']):
                logger.info(f"  Task {task.get('id', i+1)}: {task.get('description', 'No description')[:50]}...")
        
        if approval_status == 'approved':
            logger.info("Plan approved, proceeding to task execution")
            logger.info("Routing to task_selector for task execution")
            return "approved"
        elif approval_status == 'rejected':
            logger.info("Plan rejected, regenerating plan")
            return "rejected"
        else:
            logger.info(f"No approval decision (status: {approval_status}), ending workflow")
            return "end"
    
    @trace_langgraph_router("task")
    def _intelligent_task_router(self, state: AgentState) -> str:
        """Intelligent routing based on task type and requirements"""
        thread_id = state.get('thread_id', 'unknown')
        
        logger.info(f"Task router called with {len(state.get('plan', []))} tasks in plan")
        
        # Check if workflow is complete
        if self._is_workflow_complete(state):
            langfuse_service.log_custom_event("workflow_completion", {
                "thread_id": thread_id,
                "total_tasks": len(state.get('plan', [])),
                "completed_tasks": len([t for t in state.get('plan', []) if t.get('status') == 'completed'])
            })
            log_state_transition("task_execution", "compile_results", thread_id)
            logger.info("All tasks completed, compiling results")
            return "complete"
        
        # Get current task
        current_task = self._get_current_task(state)
        next_task_id = state.get('next_task_id')
        
        logger.info(f"Current task: {current_task}")
        logger.info(f"Next task ID: {next_task_id}")
        
        if not current_task:
            langfuse_service.log_custom_event("workflow_end", {
                "thread_id": thread_id,
                "reason": "no_current_task"
            })

            logger.info("No current task found, ending workflow")
            return "end"
        
        # Route based on task type
        task_type = current_task['type']
            # Log task routing decision
        langfuse_service.log_custom_event("task_routing", {
            "thread_id": thread_id,
            "task_id": current_task.get('id'),
            "task_type": task_type,
            "task_description": current_task.get('description', '')[:100]
        })

        if task_type in [TaskType.RESEARCH, TaskType.ANALYSIS, TaskType.SUMMARY]:
            logger.info(f"Routing task {current_task['id']} to research agent")
            return "research"
        elif task_type in [TaskType.CODE, TaskType.CALCULATION]:
            logger.info(f"Routing task {current_task['id']} to code agent")
            return "code"
        else:
            logger.warning(f"Unknown task type {task_type}, routing to research agent")
            return "research"
    
    def _get_next_executable_task_id(self, state: AgentState) -> int:
        """Get the next task that can be executed (dependencies satisfied)"""
        
        completed_task_ids = {
            task['id'] for task in state['plan'] 
            if task['status'] == TaskStatus.COMPLETED
        }
        
        for task in state['plan']:
            if task['status'] == TaskStatus.PENDING:
                # Check if all dependencies are satisfied
                dependencies_satisfied = all(
                    dep_id in completed_task_ids 
                    for dep_id in task['dependencies']
                )
                
                if dependencies_satisfied:
                    return task['id']
        
        return None
    
    def _get_current_task(self, state: AgentState) -> SubTask:
        """Get the current task being executed"""
        next_task_id = state.get('next_task_id')
        if next_task_id is None:
            return None
        
        for task in state['plan']:
            if task['id'] == next_task_id:
                return task
        
        return None
    
    def _is_workflow_complete(self, state: AgentState) -> bool:
        """Check if all tasks are completed"""
        if not state['plan']:
            return False
        
        return all(
            task['status'] == TaskStatus.COMPLETED 
            for task in state['plan']
        )
    
    def _mark_task_failed(self, state: AgentState, error_message: str) -> AgentState:
        """Mark current task as failed"""
        current_task = self._get_current_task(state)
        if not current_task:
            return state
        
        new_state = state.copy()
        for task in new_state['plan']:
            if task['id'] == current_task['id']:
                TimestampUtils.set_task_failed(task, error_message)
                break
        self._save_intermediate_state(new_state, f"task {current_task['id']} failed")
        return new_state
    
    def _generate_final_report(self, state: AgentState) -> str:
        """Generate final comprehensive report"""
        
        report_sections = [
            "# Clarity.ai Task Execution Report\n",
            f"**Original Request:** {state['user_request']}\n",
            f"**Execution Date:** {self._get_current_timestamp()}\n",
            "---\n"
        ]
        
        # Add task summary
        completed_tasks = [t for t in state['plan'] if t['status'] == TaskStatus.COMPLETED]
        failed_tasks = [t for t in state['plan'] if t['status'] == TaskStatus.FAILED]
        
        report_sections.append(f"## Summary\n")
        report_sections.append(f"- **Total Tasks:** {len(state['plan'])}\n")
        report_sections.append(f"- **Completed:** {len(completed_tasks)}\n")
        report_sections.append(f"- **Failed:** {len(failed_tasks)}\n\n")
        
        # Add detailed results
        report_sections.append("## Detailed Results\n\n")
        
        for task in state['plan']:
            status_emoji = "✅" if task['status'] == TaskStatus.COMPLETED else "❌"
            report_sections.append(f"### {status_emoji} Task {task['id']}: {task['description']}\n")
            report_sections.append(f"**Type:** {task['type']}\n")
            report_sections.append(f"**Status:** {task['status']}\n")
            
            if task.get('result'):
                report_sections.append(f"**Result:**\n{task['result']}\n\n")
            else:
                report_sections.append("**Result:** No result available\n\n")
        
        # Add conclusion
        if failed_tasks:
            report_sections.append("## Conclusion\n")
            report_sections.append(f"Workflow completed with {len(failed_tasks)} failed tasks. ")
            report_sections.append("Please review the failed tasks and consider re-running them.\n")
        else:
            report_sections.append("## Conclusion\n")
            report_sections.append("All tasks completed successfully! 🎉\n")
        
        return "".join(report_sections)
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp for reporting"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")