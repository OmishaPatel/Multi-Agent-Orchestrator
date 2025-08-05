from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
from src.graph.state import AgentState, SubTask, TaskType, TaskStatus, ApprovalStatus
from src.agents.planning_agent import PlanningAgent
from src.agents.research_agent import ResearchAgent
from src.agents.code_agent import CodeAgent
from src.utils.logging_config import get_logger, get_workflow_logger, log_state_transition
import asyncio

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
    
    def _planning_node(self, state: AgentState) -> AgentState:
        """Planning agent node - decomposes user request into structured tasks"""
        thread_id = state.get('thread_id', 'unkown')
        log_state_transition("start", "planning", thread_id)
        
        try:
            # Generate or regenerate plan based on feedback
            if state.get('human_approval_status') == 'rejected' and state.get('user_feedback'):
                logger.info("Regenerating plan based on user feedback")
                plan = self.planning_agent.regenerate_plan(
                    state['user_request'], 
                    state['user_feedback'],
                    state.get('plan', [])
                )
            else:
                logger.info("Generating initial plan")
                plan = self.planning_agent.generate_plan(state['user_request'])
            
            # Update state with new plan
            new_state = state.copy()
            new_state['plan'] = plan
            new_state['human_approval_status'] = 'pending'
            new_state['user_feedback'] = None
            
            # Set first task as next
            if plan:
                new_state['next_task_id'] = self._get_next_executable_task_id(new_state)
            log_state_transition("planning", "await_approval", thread_id)
            logger.info(f"Generated plan with {len(plan)} tasks")
            return new_state
            
        except Exception as e:
            logger.error(f"Planning agent failed: {e}", exc_info=True)
            # Return state with error indication
            error_state = state.copy()
            error_state['plan'] = []
            return error_state
    
    def _await_approval_node(self, state: AgentState) -> AgentState:
        """Await approval node - pauses execution for human review"""
        logger.info("Awaiting human approval for plan")
        
        # This node simply returns the state unchanged
        # The workflow will pause here due to interrupt_before configuration
        return state
    
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
                    task['status'] = TaskStatus.IN_PROGRESS
                    logger.info(f"Selected task {next_task_id}: {task['description']}")
                    break
            
            return new_state
            
        except Exception as e:
            logger.error(f"Task selector failed: {e}", exc_info=True)
            return state
    
    def _research_node(self, state: AgentState) -> AgentState:
        """Research agent node - handles research and analysis tasks"""
        thread_id = state.get('thread_id', 'unknown')
        log_state_transition("task_selection", "research_execution", thread_id)
        
        try:
            current_task = self._get_current_task(state)
            if not current_task:
                logger.warning("No current task found for research agent")
                return state
            
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
                    task['status'] = TaskStatus.COMPLETED
                    task['result'] = result
                    break
            
            log_state_transition("research_execution", "task_completed", thread_id)
            logger.info(f"Completed research task {current_task['id']}")
            return new_state
            
        except Exception as e:
            logger.error(f"Research agent failed: {e}", exc_info=True)
            # Mark task as failed
            return self._mark_task_failed(state, str(e))
    
    def _code_node(self, state: AgentState) -> AgentState:
        """Code agent node - handles coding and computational tasks"""
        thread_id = state.get('thread_id', 'unknown')
        log_state_transition("task_selection", "code_execution", thread_id)
        
        try:
            current_task = self._get_current_task(state)
            if not current_task:
                logger.warning("No current task found for code agent")
                return state
            
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
                    task['status'] = TaskStatus.COMPLETED
                    task['result'] = result
                    break
            
            log_state_transition("code_execution", "task_completed", thread_id)
            logger.info(f"Completed code task {current_task['id']}")
            return new_state
            
        except Exception as e:
            logger.error(f"Code agent failed: {e}", exc_info=True)
            # Mark task as failed
            return self._mark_task_failed(state, str(e))
    
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
    
    def _approval_router(self, state: AgentState) -> str:
        """Route based on human approval status"""
        approval_status = state.get('human_approval_status', 'pending')
        
        logger.info(f"Approval router called with status: {approval_status}")
        logger.info(f"State keys: {list(state.keys())}")
        logger.info(f"Plan has {len(state.get('plan', []))} tasks")
        
        if approval_status == 'approved':
            logger.info("Plan approved, proceeding to task execution")
            return "approved"
        elif approval_status == 'rejected':
            logger.info("Plan rejected, regenerating plan")
            return "rejected"
        else:
            logger.info(f"No approval decision (status: {approval_status}), ending workflow")
            return "end"
    
    def _intelligent_task_router(self, state: AgentState) -> str:
        """Intelligent routing based on task type and requirements"""
        
        logger.info(f"Task router called with {len(state.get('plan', []))} tasks in plan")
        
        # Check if workflow is complete
        if self._is_workflow_complete(state):
            thread_id = state.get('thread_id', 'unknown')
            log_state_transition("task_execution", "compile_results", thread_id)
            logger.info("All tasks completed, compiling results")
            return "complete"
        
        # Get current task
        current_task = self._get_current_task(state)
        next_task_id = state.get('next_task_id')
        
        logger.info(f"Current task: {current_task}")
        logger.info(f"Next task ID: {next_task_id}")
        
        if not current_task:
            logger.info("No current task found, ending workflow")
            return "end"
        
        # Route based on task type
        task_type = current_task['type']
        
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
                task['status'] = TaskStatus.FAILED
                task['result'] = f"Task failed: {error_message}"
                break
        
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