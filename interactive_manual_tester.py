#!/usr/bin/env python3
"""
Interactive Manual Tester for Clarity.ai
Comprehensive edge case testing including plan rejection, feedback loops, and error scenarios
"""

import requests
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime

class InteractiveManualTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.active_workflows = {}  # Track active workflows
        
    def print_header(self, title: str):
        """Print formatted header"""
        print(f"\n{'='*60}")
        print(f"🎯 {title}")
        print(f"{'='*60}")
    
    def print_section(self, title: str):
        """Print formatted section"""
        print(f"\n{'-'*40}")
        print(f"📋 {title}")
        print(f"{'-'*40}")
    
    def wait_with_countdown(self, seconds: int, message: str = "Waiting"):
        """Wait with countdown display"""
        for i in range(seconds, 0, -1):
            print(f"\r⏳ {message}... {i}s", end="", flush=True)
            time.sleep(1)
        print(f"\r✅ {message} complete!     ")
    
    def start_workflow(self, user_request: str, description: str = "") -> Optional[str]:
        """Start a workflow and track it"""
        self.print_section(f"Starting Workflow: {description}")
        print(f"Request: {user_request}")
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/run",
                json={"user_request": user_request},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                thread_id = data["thread_id"]
                
                # Track workflow
                self.active_workflows[thread_id] = {
                    "description": description,
                    "user_request": user_request,
                    "started_at": datetime.now(),
                    "status": "started"
                }
                
                print(f"✅ Workflow started successfully!")
                print(f"🆔 Thread ID: {thread_id}")
                print(f"📊 Status: {data['status']}")
                print(f"💬 Message: {data['message']}")
                
                return thread_id
            else:
                print(f"❌ Failed to start workflow: {response.status_code}")
                print(f"Error: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Exception starting workflow: {e}")
            return None
    
    def get_detailed_status(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed workflow status"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/status/{thread_id}")
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get status: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Exception getting status: {e}")
            return None
    
    def display_status(self, thread_id: str, show_tasks: bool = True) -> Optional[Dict[str, Any]]:
        """Display formatted workflow status"""
        data = self.get_detailed_status(thread_id)
        if not data:
            return None
        
        print(f"\n📊 Status for {thread_id[:8]}...")
        print(f"   Overall Status: {data['status']}")
        print(f"   Approval Status: {data.get('human_approval_status', 'N/A')}")
        
        # Progress
        progress = data.get('progress', {})
        print(f"   Progress: {progress.get('completion_percentage', 0):.1f}%")
        print(f"   Tasks: {progress.get('completed_tasks', 0)}/{progress.get('total_tasks', 0)}")
        
        # Current task
        current_task = data.get('current_task')
        if current_task:
            print(f"   Current Task: {current_task['description']}")
        
        # Messages
        messages = data.get('messages', [])
        if messages:
            print(f"   Latest Message: {messages[-1]}")
        
        # Tasks detail
        if show_tasks:
            tasks = data.get('tasks', [])
            if tasks:
                print(f"\n   📋 Tasks Detail:")
                for task in tasks:
                    status_icon = {
                        "pending": "⏳", 
                        "in_progress": "🔄", 
                        "completed": "✅", 
                        "failed": "❌"
                    }.get(task['status'], "❓")
                    
                    deps = f" (deps: {task.get('dependencies', [])})" if task.get('dependencies') else ""
                    print(f"      {status_icon} {task['id']}: {task['description']} [{task['status']}]{deps}")
                    
                    if task.get('result'):
                        result_preview = task['result'][:100] + "..." if len(task['result']) > 100 else task['result']
                        print(f"         Result: {result_preview}")
        
        # Final report
        if data.get('final_report'):
            print(f"\n   📄 Final Report Available ({len(data['final_report'])} chars)")
            report_preview = data['final_report'][:200] + "..." if len(data['final_report']) > 200 else data['final_report']
            print(f"   Preview: {report_preview}")
        
        # User feedback if any
        if data.get('user_feedback'):
            print(f"\n   💬 User Feedback: {data['user_feedback']}")
        
        # Debug information for troubleshooting
        if data.get('status') in ['plan_rejected', 'pending_approval']:
            print(f"\n   🔍 Debug Info:")
            print(f"      - Checkpointing: {data.get('checkpointing_type', 'unknown')}")
            print(f"      - Messages: {len(data.get('messages', []))} total")
            if data.get('messages'):
                print(f"      - Latest: {data['messages'][-1]}")
        
        return data
    
    def approve_plan(self, thread_id: str, approved: bool = True, feedback: str = None) -> bool:
        """Approve or reject a plan with optional feedback"""
        action = "Approving" if approved else "Rejecting"
        print(f"\n{'✅' if approved else '❌'} {action} plan for {thread_id[:8]}...")
        
        if feedback:
            print(f"💬 Feedback: {feedback}")
        
        try:
            payload = {"approved": approved}
            if feedback:
                payload["feedback"] = feedback
            
            response = self.session.post(
                f"{self.base_url}/api/v1/approve/{thread_id}",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Plan {action.lower()} successfully!")
                print(f"📊 New Status: {data['status']}")
                print(f"💬 Message: {data['message']}")
                
                # Update tracking
                if thread_id in self.active_workflows:
                    self.active_workflows[thread_id]["status"] = data['status']
                
                return True
            else:
                print(f"❌ Failed to {action.lower()} plan: {response.status_code}")
                print(f"Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Exception {action.lower()} plan: {e}")
            return False
    
    def test_plan_rejection_cycle(self):
        """Test plan rejection and regeneration cycle"""
        self.print_header("Plan Rejection & Regeneration Test")
        
        # Start with a request that should generate a multi-step plan
        user_request = "Research the benefits of meditation, write Python code to analyze survey data about meditation practices, and create a comprehensive report with recommendations"
        
        thread_id = self.start_workflow(user_request, "Plan Rejection Test")
        if not thread_id:
            return
        
        # Wait for planning
        self.wait_with_countdown(8, "Waiting for initial planning")
        
        # Check initial status
        print(f"\n📊 Checking initial plan...")
        initial_status = self.display_status(thread_id)
        
        if not initial_status or initial_status.get('status') != 'pending_approval':
            print(f"⚠️  Expected pending_approval status, got: {initial_status.get('status') if initial_status else 'None'}")
            return
        
        # Show the initial plan
        tasks = initial_status.get('tasks', [])
        print(f"\n📋 Initial Plan ({len(tasks)} tasks):")
        for task in tasks:
            print(f"   • {task['description']} ({task['type']})")
        
        # Reject the plan with specific feedback
        feedback_scenarios = [
            "Please add more detailed research on different types of meditation (mindfulness, transcendental, etc.) and include statistical analysis in the Python code",
            "The plan is too complex. Please simplify it to focus only on basic meditation benefits and a simple data summary",
            "Please add a task to create visualizations and ensure the report includes actionable recommendations for beginners"
        ]
        
        for i, feedback in enumerate(feedback_scenarios, 1):
            print(f"\n🔄 Rejection Cycle {i}/3")
            print(f"💬 Feedback: {feedback}")
            
            # Reject with feedback
            if not self.approve_plan(thread_id, approved=False, feedback=feedback):
                print("❌ Failed to reject plan, stopping test")
                return
            
            # Wait for re-planning
            self.wait_with_countdown(10, f"Waiting for re-planning (cycle {i})")
            
            # Check new plan with retry logic
            print(f"\n📊 Checking revised plan (cycle {i})...")
            
            # Retry logic for plan regeneration
            max_retries = 3
            revised_status = None
            
            for retry in range(max_retries):
                revised_status = self.display_status(thread_id)
                
                if revised_status and revised_status.get('status') == 'pending_approval':
                    break
                elif revised_status and revised_status.get('status') == 'plan_rejected':
                    if retry < max_retries - 1:
                        print(f"⏳ Plan still regenerating, waiting... (attempt {retry + 1}/{max_retries})")
                        self.wait_with_countdown(5, "Waiting for plan regeneration")
                    else:
                        print(f"⚠️  Plan regeneration seems stuck after {max_retries} attempts")
                        break
                else:
                    break
            
            if revised_status and revised_status.get('status') == 'pending_approval':
                revised_tasks = revised_status.get('tasks', [])
                print(f"\n📋 Revised Plan ({len(revised_tasks)} tasks):")
                for task in revised_tasks:
                    print(f"   • {task['description']} ({task['type']})")
                
                # Compare with initial plan
                if len(revised_tasks) != len(tasks):
                    print(f"📈 Plan complexity changed: {len(tasks)} → {len(revised_tasks)} tasks")
                
                # Ask user if they want to continue or approve
                print(f"\n🤔 What would you like to do?")
                print(f"1. Continue with next rejection cycle")
                print(f"2. Approve this revised plan")
                print(f"3. Stop test")
                
                choice = input("Enter choice (1-3): ").strip()
                
                if choice == "2":
                    print(f"\n✅ Approving revised plan...")
                    if self.approve_plan(thread_id, approved=True):
                        self.wait_with_countdown(15, "Waiting for task execution")
                        final_status = self.display_status(thread_id)
                        print(f"\n🎉 Final workflow status: {final_status.get('status') if final_status else 'Unknown'}")
                    break
                elif choice == "3":
                    print(f"\n🛑 Test stopped by user")
                    break
                # Continue with next cycle for choice "1"
            else:
                current_status = revised_status.get('status') if revised_status else 'None'
                print(f"⚠️  Unexpected status after rejection: {current_status}")
                
                # Show debugging information
                if revised_status:
                    print(f"📊 Debug info:")
                    print(f"   - Approval status: {revised_status.get('human_approval_status', 'unknown')}")
                    print(f"   - Tasks count: {len(revised_status.get('tasks', []))}")
                    print(f"   - Messages: {revised_status.get('messages', [])}")
                    
                    # Ask if user wants to continue anyway
                    continue_anyway = input(f"\nContinue test anyway? (y/n): ").strip().lower()
                    if continue_anyway != 'y':
                        break
                else:
                    print(f"❌ Could not get workflow status")
                    break
        
        print(f"\n✨ Plan rejection test completed for thread: {thread_id}")
    
    def test_edge_cases(self):
        """Test various edge cases"""
        self.print_header("Edge Cases Testing")
        
        edge_cases = [
            {
                "name": "Empty Request",
                "request": "",
                "expected": "Should fail with validation error"
            },
            {
                "name": "Very Long Request",
                "request": "A" * 6000,  # Exceeds 5000 char limit
                "expected": "Should fail with validation error"
            },
            {
                "name": "Ambiguous Request",
                "request": "Do something",
                "expected": "Should ask for clarification or create generic plan"
            },
            {
                "name": "Single Word Request",
                "request": "Python",
                "expected": "Should create a reasonable plan around Python"
            },
            {
                "name": "Contradictory Request",
                "request": "Write code without using any programming language",
                "expected": "Should handle contradiction gracefully"
            },
            {
                "name": "Multi-language Request",
                "request": "Écrivez un rapport sur l'intelligence artificielle en français et créez du code Python",
                "expected": "Should handle mixed language request"
            }
        ]
        
        for i, case in enumerate(edge_cases, 1):
            print(f"\n🧪 Edge Case {i}: {case['name']}")
            print(f"Request: {case['request'][:100]}{'...' if len(case['request']) > 100 else ''}")
            print(f"Expected: {case['expected']}")
            
            thread_id = self.start_workflow(case['request'], f"Edge Case: {case['name']}")
            
            if thread_id:
                self.wait_with_countdown(5, "Waiting for processing")
                status = self.display_status(thread_id, show_tasks=False)
                
                if status:
                    print(f"✅ Result: {status['status']}")
                else:
                    print(f"❌ Failed to get status")
            
            # Ask if user wants to continue
            if i < len(edge_cases):
                continue_test = input(f"\nContinue to next edge case? (y/n): ").strip().lower()
                if continue_test != 'y':
                    break
    
    def test_approval_edge_cases(self):
        """Test approval-related edge cases"""
        self.print_header("Approval Edge Cases Testing")
        
        # Start a workflow
        thread_id = self.start_workflow(
            "Create a simple Python calculator and write documentation for it",
            "Approval Edge Cases Test"
        )
        
        if not thread_id:
            return
        
        self.wait_with_countdown(5, "Waiting for planning")
        status = self.display_status(thread_id)
        
        if not status or status.get('status') != 'pending_approval':
            print(f"⚠️  Workflow not in pending_approval state")
            return
        
        # Test various approval scenarios
        scenarios = [
            {
                "name": "Approval without feedback",
                "approved": True,
                "feedback": None
            },
            {
                "name": "Rejection without feedback",
                "approved": False,
                "feedback": None,
                "should_fail": True
            },
            {
                "name": "Rejection with empty feedback",
                "approved": False,
                "feedback": "",
                "should_fail": True
            },
            {
                "name": "Rejection with valid feedback",
                "approved": False,
                "feedback": "Please add error handling to the calculator and include unit tests"
            }
        ]
        
        for scenario in scenarios:
            print(f"\n🧪 Testing: {scenario['name']}")
            
            success = self.approve_plan(
                thread_id, 
                approved=scenario['approved'], 
                feedback=scenario.get('feedback')
            )
            
            should_fail = scenario.get('should_fail', False)
            
            if should_fail and success:
                print(f"⚠️  Expected failure but got success")
            elif not should_fail and not success:
                print(f"⚠️  Expected success but got failure")
            else:
                print(f"✅ Behaved as expected")
            
            # Only test first scenario that works
            if success and not should_fail:
                break
    
    def test_langgraph_streaming_implementation(self):
        """Test the new LangGraph streaming implementation"""
        self.print_header("LangGraph Streaming Implementation Test")
        
        print("🎯 This test validates our new LangGraph streaming approach:")
        print("   • Singleton WorkflowFactory maintains workflow instances")
        print("   • LangGraph streaming replaces manual execution")
        print("   • State persistence works correctly")
        print("   • Workflow continuity across API calls")
        
        # Test 1: Basic streaming workflow
        print(f"\n🧪 Test 1: Basic Streaming Workflow")
        thread_id = self.start_workflow(
            "Research the benefits of exercise and create a simple summary",
            "LangGraph Streaming Test"
        )
        
        if not thread_id:
            print("❌ Failed to start workflow")
            return
        
        # Wait and check planning
        self.wait_with_countdown(5, "Waiting for LangGraph planning")
        status = self.display_status(thread_id)
        
        if not status or status.get('status') != 'pending_approval':
            print(f"❌ Expected pending_approval, got: {status.get('status') if status else 'None'}")
            return
        
        print(f"✅ Planning completed successfully with LangGraph")
        
        # Test 2: Approve and validate streaming execution
        print(f"\n🧪 Test 2: LangGraph Streaming Execution")
        if not self.approve_plan(thread_id, approved=True):
            print("❌ Failed to approve plan")
            return
        
        print(f"✅ Plan approved - LangGraph streaming should begin")
        
        # Monitor streaming execution with detailed logging
        print(f"\n📊 Monitoring LangGraph streaming execution...")
        
        max_checks = 15
        for check in range(1, max_checks + 1):
            self.wait_with_countdown(3, f"Monitoring streaming (check {check}/{max_checks})")
            
            status = self.display_status(thread_id)
            if not status:
                print(f"❌ Lost connection to workflow")
                break
            
            current_status = status.get('status')
            print(f"   🔄 Check {check}: Status = {current_status}")
            
            # Log streaming progress
            progress = status.get('progress', {})
            completed = progress.get('completed_tasks', 0)
            total = progress.get('total_tasks', 0)
            
            if total > 0:
                print(f"   📈 Progress: {completed}/{total} tasks completed ({progress.get('completion_percentage', 0):.1f}%)")
            
            # Check for completion
            if current_status == 'completed':
                print(f"✅ Workflow completed successfully!")
                
                # Validate final state
                if status.get('final_report'):
                    print(f"✅ Final report generated ({len(status['final_report'])} chars)")
                else:
                    print(f"⚠️  No final report found")
                
                # Show task completion
                tasks = status.get('tasks', [])
                completed_tasks = [t for t in tasks if t.get('status') == 'completed']
                print(f"✅ Task completion: {len(completed_tasks)}/{len(tasks)} tasks completed")
                
                break
            elif current_status in ['failed', 'error']:
                print(f"❌ Workflow failed with status: {current_status}")
                break
            elif current_status in ['in_progress', 'ready_for_execution']:
                print(f"   ⏳ LangGraph streaming in progress...")
                continue
            else:
                print(f"   📊 Current status: {current_status}")
        else:
            print(f"⚠️  Workflow didn't complete within {max_checks} checks")
            final_status = self.display_status(thread_id)
            if final_status:
                print(f"   Final status: {final_status.get('status')}")
        
        # Test 3: Validate singleton behavior
        print(f"\n🧪 Test 3: Singleton WorkflowFactory Validation")
        
        # Make multiple status calls to ensure same workflow instance is used
        print(f"Making multiple status calls to validate singleton behavior...")
        
        for i in range(3):
            status = self.get_detailed_status(thread_id)
            if status:
                checkpointing = status.get('checkpointing_type', 'unknown')
                print(f"   Status call {i+1}: Checkpointing = {checkpointing}")
            else:
                print(f"   Status call {i+1}: Failed")
        
        print(f"✅ Singleton validation completed")
        
        # Test 4: State persistence validation
        print(f"\n🧪 Test 4: State Persistence Validation")
        
        final_status = self.get_detailed_status(thread_id)
        if final_status:
            # Check that state is properly persisted
            has_plan = len(final_status.get('plan', [])) > 0
            has_results = len(final_status.get('task_results', {})) > 0
            has_messages = len(final_status.get('messages', [])) > 0
            
            print(f"   State persistence check:")
            print(f"   ✅ Plan preserved: {has_plan}")
            print(f"   ✅ Task results preserved: {has_results}")
            print(f"   ✅ Messages preserved: {has_messages}")
            
            if has_plan and has_results and has_messages:
                print(f"✅ State persistence validation passed")
            else:
                print(f"⚠️  Some state may not be properly persisted")
        else:
            print(f"❌ Could not validate state persistence")
        
        print(f"\n🎉 LangGraph Streaming Implementation Test Completed!")
        print(f"Thread ID: {thread_id}")
        
        # Test 5: Crash Recovery Simulation
        print(f"\n🧪 Test 5: Crash Recovery Simulation")
        print(f"💡 This simulates what happens if the application restarts")
        print(f"   The workflow state should be recoverable from Redis")
        
        # Simulate getting status after "restart" (new API call)
        print(f"Simulating application restart by making fresh status call...")
        recovery_status = self.get_detailed_status(thread_id)
        
        if recovery_status:
            print(f"✅ Workflow state recovered successfully after simulated restart")
            print(f"   Status: {recovery_status.get('status')}")
            print(f"   Plan tasks: {len(recovery_status.get('plan', []))}")
            print(f"   Task results: {len(recovery_status.get('task_results', {}))}")
            print(f"   Final report: {'Present' if recovery_status.get('final_report') else 'Not present'}")
        else:
            print(f"❌ Failed to recover workflow state after simulated restart")
        
        print(f"\n🎉 Complete LangGraph Streaming Implementation Test Finished!")
        print(f"Thread ID: {thread_id}")
        
        return thread_id

    def test_concurrent_workflows(self):
        """Test multiple concurrent workflows"""
        self.print_header("Concurrent Workflows Test")
        
        requests = [
            "Calculate fibonacci sequence up to 10 numbers",
            "Research latest Python frameworks",
            "Write a simple sorting algorithm",
            "Analyze pros and cons of remote work"
        ]
        
        thread_ids = []
        
        # Start multiple workflows
        for i, req in enumerate(requests, 1):
            print(f"\n🚀 Starting workflow {i}/4...")
            thread_id = self.start_workflow(req, f"Concurrent Test {i}")
            if thread_id:
                thread_ids.append(thread_id)
        
        print(f"\n✅ Started {len(thread_ids)} concurrent workflows")
        
        # Monitor all workflows
        self.wait_with_countdown(8, "Waiting for all workflows to plan")
        
        print(f"\n📊 Status of all concurrent workflows:")
        for i, thread_id in enumerate(thread_ids, 1):
            print(f"\n--- Workflow {i} ({thread_id[:8]}...) ---")
            self.display_status(thread_id, show_tasks=False)
    
    def interactive_workflow_manager(self):
        """Interactive workflow management interface"""
        self.print_header("Interactive Workflow Manager")
        
        while True:
            print(f"\n🎮 Workflow Manager Menu:")
            print(f"1. Start new workflow")
            print(f"2. Check workflow status")
            print(f"3. Approve/Reject workflow")
            print(f"4. List active workflows")
            print(f"5. Test plan rejection cycle")
            print(f"6. Test edge cases")
            print(f"7. Test approval edge cases")
            print(f"8. Test concurrent workflows")
            print(f"9. Test LangGraph streaming implementation")
            print(f"10. Exit")
            
            choice = input(f"\nEnter choice (1-10): ").strip()
            
            if choice == "1":
                user_request = input("Enter your request: ").strip()
                if user_request:
                    description = input("Enter description (optional): ").strip()
                    self.start_workflow(user_request, description or "Manual Test")
            
            elif choice == "2":
                thread_id = input("Enter thread ID (or partial): ").strip()
                if thread_id:
                    # Find matching thread ID
                    matches = [tid for tid in self.active_workflows.keys() if tid.startswith(thread_id)]
                    if matches:
                        self.display_status(matches[0])
                    else:
                        print(f"❌ No workflow found matching: {thread_id}")
            
            elif choice == "3":
                thread_id = input("Enter thread ID (or partial): ").strip()
                if thread_id:
                    matches = [tid for tid in self.active_workflows.keys() if tid.startswith(thread_id)]
                    if matches:
                        full_thread_id = matches[0]
                        
                        # Check if it needs approval
                        status = self.get_detailed_status(full_thread_id)
                        if status and status.get('status') == 'pending_approval':
                            approve = input("Approve plan? (y/n): ").strip().lower() == 'y'
                            feedback = None
                            
                            if not approve:
                                feedback = input("Enter feedback: ").strip()
                                if not feedback:
                                    print("❌ Feedback required for rejection")
                                    continue
                            
                            self.approve_plan(full_thread_id, approve, feedback)
                        else:
                            print(f"⚠️  Workflow not in pending_approval state: {status.get('status') if status else 'Unknown'}")
                    else:
                        print(f"❌ No workflow found matching: {thread_id}")
            
            elif choice == "4":
                if self.active_workflows:
                    print(f"\n📋 Active Workflows ({len(self.active_workflows)}):")
                    for thread_id, info in self.active_workflows.items():
                        print(f"   🆔 {thread_id[:8]}... - {info['description']}")
                        print(f"      Started: {info['started_at'].strftime('%H:%M:%S')}")
                        print(f"      Request: {info['user_request'][:60]}...")
                else:
                    print(f"📭 No active workflows")
            
            elif choice == "5":
                self.test_plan_rejection_cycle()
            
            elif choice == "6":
                self.test_edge_cases()
            
            elif choice == "7":
                self.test_approval_edge_cases()
            
            elif choice == "8":
                self.test_concurrent_workflows()
            
            elif choice == "9":
                self.test_langgraph_streaming_implementation()
            
            elif choice == "10":
                print(f"👋 Goodbye!")
                break
            
            else:
                print(f"❌ Invalid choice")

def main():
    """Main interactive testing interface"""
    tester = InteractiveManualTester()
    
    print("🧪 Clarity.ai Interactive Manual Tester")
    print("🎯 Comprehensive Edge Case Testing Tool")
    print("=" * 50)
    
    # Quick system check
    try:
        response = requests.get(f"{tester.base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running and healthy")
        else:
            print(f"⚠️  Backend health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        print(f"💡 Make sure the backend is running at {tester.base_url}")
        return
    
    # Start interactive manager
    tester.interactive_workflow_manager()

if __name__ == "__main__":
    main()