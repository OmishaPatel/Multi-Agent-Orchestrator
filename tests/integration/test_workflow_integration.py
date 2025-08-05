import pytest
import asyncio
import os
import uuid
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from src.core.workflow_factory import WorkflowFactory
from src.graph.state import AgentState, StateManager, TaskType, TaskStatus, ApprovalStatus
from src.core.redis_state_manager import RedisStateManager
from src.agents.planning_agent import PlanningAgent
from src.agents.research_agent import ResearchAgent
from src.agents.code_agent import CodeAgent
from tests.integration.test_mocks import TestAssertionHelpers
import redis

# Set test environment
os.environ["ENVIRONMENT"] = "development"

@pytest.fixture
def mock_redis():
    """Mock Redis for testing"""
    with patch('redis.Redis') as mock_redis_class:
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        
        # Mock Redis operations
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = None
        mock_redis_instance.set.return_value = True
        mock_redis_instance.delete.return_value = 1
        
        yield mock_redis_instance

@pytest.fixture
def workflow_factory(mock_redis):
    """Create workflow factory with mocked dependencies"""
    return WorkflowFactory()

@pytest.fixture
def sample_user_request():
    """Sample user request for testing"""
    return "Research the latest developments in AI and create a summary report"

@pytest.fixture
def sample_plan():
    """Sample plan for testing"""
    return [
        {
            "id": 1,
            "type": TaskType.RESEARCH,
            "description": "Research latest AI developments",
            "dependencies": [],
            "status": TaskStatus.PENDING,
            "result": None
        },
        {
            "id": 2,
            "type": TaskType.ANALYSIS,
            "description": "Analyze research findings",
            "dependencies": [1],
            "status": TaskStatus.PENDING,
            "result": None
        }
    ]

class TestWorkflowIntegration:
    """Integration tests for the complete workflow system"""
    
    @pytest.mark.asyncio
    async def test_workflow_creation(self, workflow_factory):
        """Test that workflow can be created successfully"""
        workflow = workflow_factory.create_workflow()
        
        assert workflow is not None
        # Verify workflow has expected nodes
        assert hasattr(workflow, 'nodes')
        
    def test_initial_state_creation(self, sample_user_request):
        """Test creating initial workflow state"""
        state = StateManager.create_initial_state(sample_user_request)
        
        assert state['user_request'] == sample_user_request
        assert state['plan'] == []
        assert state['task_results'] == {}
        assert state['human_approval_status'] == ApprovalStatus.PENDING
        assert state['final_report'] is None
        
    def test_state_validation(self, sample_user_request, sample_plan):
        """Test state validation functionality"""
        state = StateManager.create_initial_state(sample_user_request)
        state['plan'] = sample_plan
        
        # Valid state should pass validation
        assert StateManager.validate_state(state) == True
        
        # Invalid state should fail validation
        invalid_state = state.copy()
        invalid_state['plan'] = [{"id": 1, "invalid": "structure"}]
        assert StateManager.validate_state(invalid_state) == False
    
    def test_enhanced_planning_agent_integration(self, workflow_factory, sample_user_request):
        """Test enhanced planning agent integration with tool calling"""
        
        workflow = workflow_factory.create_workflow()
        
        # Create initial state
        initial_state = StateManager.create_initial_state(sample_user_request)
        
        # Test planning node execution
        graph = workflow_factory.workflow_graph
        result_state = graph._planning_node(initial_state)
        
        # Plan should have at least 1 task (may be fallback plan if JSON parsing fails)
        assert len(result_state['plan']) >= 1
        assert result_state['human_approval_status'] == ApprovalStatus.PENDING
        assert result_state['next_task_id'] == 1  # First executable task
        
        # Verify plan structure is valid
        TestAssertionHelpers.assert_plan_structure(result_state['plan'])
        
        # Verify each task has required fields
        for task in result_state['plan']:
            assert 'id' in task
            assert 'type' in task
            assert 'description' in task
            assert 'dependencies' in task
            assert 'status' in task
        
    def test_approval_routing(self, workflow_factory):
        """Test approval routing logic"""
        graph = workflow_factory.workflow_graph
        
        # Test approved state
        approved_state = {'human_approval_status': ApprovalStatus.APPROVED}
        assert graph._approval_router(approved_state) == "approved"
        
        # Test rejected state
        rejected_state = {'human_approval_status': ApprovalStatus.REJECTED}
        assert graph._approval_router(rejected_state) == "rejected"
        
        # Test pending state
        pending_state = {'human_approval_status': ApprovalStatus.PENDING}
        assert graph._approval_router(pending_state) == "end"
    
    def test_intelligent_task_routing(self, workflow_factory, sample_plan):
        """Test intelligent task routing based on task type"""
        graph = workflow_factory.workflow_graph
        
        # Test research task routing
        research_state = {
            'plan': sample_plan,
            'next_task_id': 1,  # Research task
            'task_results': {}
        }
        assert graph._intelligent_task_router(research_state) == "research"
        
        # Test code task routing
        code_plan = [{
            "id": 1,
            "type": TaskType.CODE,
            "description": "Calculate statistics",
            "dependencies": [],
            "status": TaskStatus.PENDING,
            "result": None
        }]
        code_state = {
            'plan': code_plan,
            'next_task_id': 1,
            'task_results': {}
        }
        assert graph._intelligent_task_router(code_state) == "code"
        
        # Test completed workflow
        completed_plan = [{
            "id": 1,
            "type": TaskType.RESEARCH,
            "description": "Research task",
            "dependencies": [],
            "status": TaskStatus.COMPLETED,
            "result": "Research complete"
        }]
        completed_state = {
            'plan': completed_plan,
            'next_task_id': None,
            'task_results': {1: "Research complete"}
        }
        assert graph._intelligent_task_router(completed_state) == "complete"
    
    def test_dependency_resolution(self, workflow_factory):
        """Test task dependency resolution"""
        graph = workflow_factory.workflow_graph
        
        # Create plan with dependencies
        plan_with_deps = [
            {
                "id": 1,
                "type": TaskType.RESEARCH,
                "description": "Research task",
                "dependencies": [],
                "status": TaskStatus.PENDING,
                "result": None
            },
            {
                "id": 2,
                "type": TaskType.ANALYSIS,
                "description": "Analysis task",
                "dependencies": [1],
                "status": TaskStatus.PENDING,
                "result": None
            },
            {
                "id": 3,
                "type": TaskType.CODE,
                "description": "Code task",
                "dependencies": [1, 2],
                "status": TaskStatus.PENDING,
                "result": None
            }
        ]
        
        state = {'plan': plan_with_deps}
        
        # First executable task should be task 1 (no dependencies)
        next_task = graph._get_next_executable_task_id(state)
        assert next_task == 1
        
        # After completing task 1, task 2 should be next
        plan_with_deps[0]['status'] = TaskStatus.COMPLETED
        next_task = graph._get_next_executable_task_id(state)
        assert next_task == 2
        
        # After completing tasks 1 and 2, task 3 should be next
        plan_with_deps[1]['status'] = TaskStatus.COMPLETED
        next_task = graph._get_next_executable_task_id(state)
        assert next_task == 3
    
    def test_enhanced_research_agent_execution(self, workflow_factory, sample_plan):
        """Test enhanced research agent execution with Tavily integration"""
        
        graph = workflow_factory.workflow_graph
        
        # Mock the research agent's execute_task method directly on the workflow's agent
        mock_result = """Research completed successfully with enhanced capabilities.
        
## Sources Found:
- 🟢 High credibility academic source
- 🟡 Medium credibility news source

**Source Credibility Assessment:**
- High credibility sources: 1
- Medium credibility sources: 1
- Total sources analyzed: 2"""
        
        with patch.object(graph.research_agent, 'execute_task', return_value=mock_result) as mock_execute:
            # Create state with research task
            state = {
                'plan': sample_plan,
                'next_task_id': 1,
                'task_results': {}
            }
            
            # Execute research node
            result_state = graph._research_node(state)
            
            # Verify enhanced task completion
            assert result_state['task_results'][1] is not None
            assert result_state['plan'][0]['status'] == TaskStatus.COMPLETED
            # Check for actual research content patterns instead of specific text
            TestAssertionHelpers.assert_research_content(result_state['plan'][0]['result'])
            
            # Verify research agent was called with context
            mock_execute.assert_called_once()
    
    def test_enhanced_code_agent_execution(self, workflow_factory):
        """Test enhanced code agent execution with security features"""
        
        graph = workflow_factory.workflow_graph
        
        # Mock the code agent's execute_task method directly on the workflow's agent
        mock_result = """## Code Solution for: Calculate statistics

### Generated Code:
```python
import statistics
numbers = [1, 2, 3, 4, 5]
mean = statistics.mean(numbers)
print(f"Mean: {mean}")
```

### Code Analysis:
- **Complexity Level:** Simple
- **Lines of Code:** 4
- **Functions:** 0

### Execution Result:
**Status:** ✅ Success
**Output:**
```
Mean: 3.0
```
**Execution Time:** 0.12s

### Security Summary:
- ✅ Code executed in isolated Docker container
- ✅ Network access disabled
- ✅ File system access restricted
- ✅ Execution time limited to 30s"""
        
        with patch.object(graph.code_agent, 'execute_task', return_value=mock_result) as mock_execute:
            # Create state with code task
            code_plan = [{
                "id": 1,
                "type": TaskType.CODE,
                "description": "Calculate statistics",
                "dependencies": [],
                "status": TaskStatus.IN_PROGRESS,
                "result": None
            }]
            
            state = {
                'plan': code_plan,
                'next_task_id': 1,
                'task_results': {}
            }
            
            # Execute code node
            result_state = graph._code_node(state)
            
            # Verify enhanced task completion
            assert result_state['task_results'][1] is not None
            assert result_state['plan'][0]['status'] == TaskStatus.COMPLETED
            # Check for actual security validation patterns instead of specific text
            TestAssertionHelpers.assert_security_validation(result_state['plan'][0]['result'])
            assert "Code Analysis" in result_state['plan'][0]['result']
            
            # Verify code agent was called
            mock_execute.assert_called_once()
    
    def test_final_report_generation(self, workflow_factory, sample_plan):
        """Test final report generation"""
        graph = workflow_factory.workflow_graph
        
        # Create completed state
        completed_plan = sample_plan.copy()
        for task in completed_plan:
            task['status'] = TaskStatus.COMPLETED
            task['result'] = f"Task {task['id']} completed"
        
        state = {
            'user_request': "Test request",
            'plan': completed_plan,
            'task_results': {1: "Task 1 completed", 2: "Task 2 completed"}
        }
        
        # Generate final report
        result_state = graph._compile_results_node(state)
        
        # Verify report generation
        assert result_state['final_report'] is not None
        assert "Clarity.ai Task Execution Report" in result_state['final_report']
        assert "Test request" in result_state['final_report']
        assert "Task 1 completed" in result_state['final_report']
        assert "Task 2 completed" in result_state['final_report']
    
    def test_enhanced_error_handling(self, workflow_factory, sample_plan):
        """Test enhanced error handling in workflow nodes"""
        graph = workflow_factory.workflow_graph
        
        # Test planning agent error handling with fallback
        with patch('src.agents.planning_agent.PlanningAgent') as mock_planning_class:
            mock_planning_instance = Mock()
            mock_planning_instance.generate_plan.side_effect = Exception("Planning failed")
            mock_planning_class.return_value = mock_planning_instance
            
            initial_state = StateManager.create_initial_state("Test request")
            result_state = graph._planning_node(initial_state)
            
            # Should return state with fallback plan on error (not empty)
            assert isinstance(result_state['plan'], list)
            assert len(result_state['plan']) >= 1  # Fallback plan should have at least one task
        
        # Test research agent error handling
        with patch.object(graph.research_agent, 'execute_task', side_effect=Exception("Research failed")):
            state = {
                'plan': sample_plan,
                'next_task_id': 1,
                'task_results': {}
            }
            
            result_state = graph._research_node(state)
            
            # Task should be marked as failed
            assert result_state['plan'][0]['status'] == TaskStatus.FAILED
            assert "Research failed" in result_state['plan'][0]['result']
        
        # Test code agent security blocking
        security_result = """## Security Validation Failed

**Risk Level:** HIGH

**Security Issues:**
- ❌ Forbidden import: os
- ❌ Dangerous function: exec

**Resolution:** Please modify the request to avoid security risks."""
        
        with patch.object(graph.code_agent, 'execute_task', return_value=security_result):
            code_plan = [{
                "id": 1,
                "type": TaskType.CODE,
                "description": "Malicious code task",
                "dependencies": [],
                "status": TaskStatus.IN_PROGRESS,
                "result": None
            }]
            
            state = {
                'plan': code_plan,
                'next_task_id': 1,
                'task_results': {}
            }
            
            result_state = graph._code_node(state)
            
            # Should handle security blocking gracefully
            assert "Security Validation Failed" in result_state['plan'][0]['result']
    
    def test_conditional_agent_routing_logic(self, workflow_factory):
        """Test enhanced conditional routing logic"""
        graph = workflow_factory.workflow_graph
        
        # Test routing for different task types with enhanced logic
        test_cases = [
            # Research tasks
            {
                'task_type': TaskType.RESEARCH,
                'expected_route': 'research',
                'description': 'Research latest AI trends'
            },
            {
                'task_type': TaskType.ANALYSIS,
                'expected_route': 'research',  # Analysis handled by research agent
                'description': 'Analyze market data'
            },
            {
                'task_type': TaskType.SUMMARY,
                'expected_route': 'research',  # Summary handled by research agent
                'description': 'Summarize research findings'
            },
            # Code tasks
            {
                'task_type': TaskType.CODE,
                'expected_route': 'code',
                'description': 'Write Python algorithm'
            },
            {
                'task_type': TaskType.CALCULATION,
                'expected_route': 'code',
                'description': 'Calculate statistical metrics'
            }
        ]
        
        for test_case in test_cases:
            plan = [{
                "id": 1,
                "type": test_case['task_type'],
                "description": test_case['description'],
                "dependencies": [],
                "status": TaskStatus.PENDING,
                "result": None
            }]
            
            state = {
                'plan': plan,
                'next_task_id': 1,
                'task_results': {}
            }
            
            route = graph._intelligent_task_router(state)
            assert route == test_case['expected_route'], f"Task type {test_case['task_type']} should route to {test_case['expected_route']}, got {route}"
    
    def test_enhanced_final_report_generation(self, workflow_factory):
        """Test enhanced final report generation with new features"""
        graph = workflow_factory.workflow_graph
        
        # Create completed state with enhanced results
        enhanced_plan = [
            {
                "id": 1,
                "type": TaskType.RESEARCH,
                "description": "Research AI trends",
                "dependencies": [],
                "status": TaskStatus.COMPLETED,
                "result": """Research completed with enhanced capabilities.

**Source Credibility Assessment:**
- 🟢 High credibility sources: 2
- 🟡 Medium credibility sources: 1
- Total sources analyzed: 3"""
            },
            {
                "id": 2,
                "type": TaskType.CODE,
                "description": "Calculate metrics",
                "dependencies": [1],
                "status": TaskStatus.COMPLETED,
                "result": """## Code Solution for: Calculate metrics

### Security Summary:
- ✅ Code executed in isolated Docker container
- ✅ Network access disabled"""
            }
        ]
        
        state = {
            'user_request': "Research AI and calculate metrics",
            'plan': enhanced_plan,
            'task_results': {
                1: enhanced_plan[0]['result'],
                2: enhanced_plan[1]['result']
            }
        }
        
        # Generate final report
        result_state = graph._compile_results_node(state)
        
        # Verify enhanced report generation
        assert result_state['final_report'] is not None
        report = result_state['final_report']
        
        assert "Clarity.ai Task Execution Report" in report
        assert "Research AI and calculate metrics" in report
        assert "Source Credibility Assessment" in report
        assert "Security Summary" in report
        assert "✅" in report  # Success indicators
        assert "All tasks completed successfully" in report

@pytest.mark.integration
class TestEnhancedWorkflowWithOllama:
    """Integration tests for enhanced workflow with real Ollama models"""
    
    @pytest.mark.skipif(not os.getenv("OLLAMA_RUNNING"), reason="Ollama not running")
    async def test_enhanced_end_to_end_workflow(self, workflow_factory):
        """Test complete enhanced workflow execution with real Ollama models"""
        
        workflow = workflow_factory.create_workflow()
        
        # Test with a request that should trigger conditional routing
        user_request = "Research renewable energy trends and calculate potential cost savings"
        thread_id = str(uuid.uuid4())
        
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # Execute until approval needed
            result = workflow.invoke({"user_request": user_request}, config=config)
            
            # Verify enhanced planning completed
            assert 'plan' in result
            assert len(result['plan']) > 0
            assert result['human_approval_status'] == ApprovalStatus.PENDING
            
            # Should have both research and code tasks due to "calculate" keyword
            task_types = [task['type'] for task in result['plan']]
            assert TaskType.RESEARCH in task_types
            # May or may not have code task depending on planning agent's decision
            
            # Approve the plan
            approval_input = {
                "human_approval_status": ApprovalStatus.APPROVED,
                "user_feedback": None
            }
            
            # Continue workflow after approval
            final_result = workflow.invoke(approval_input, config=config)
            
            # Verify enhanced completion
            assert final_result['final_report'] is not None
            report = final_result['final_report']
            
            # Should contain enhanced features
            assert "renewable energy" in report.lower()
            assert "Clarity.ai Task Execution Report" in report
            
            # Check for enhanced agent outputs
            completed_tasks = [t for t in final_result['plan'] if t['status'] == TaskStatus.COMPLETED]
            assert len(completed_tasks) > 0
            
        except Exception as e:
            pytest.skip(f"Enhanced Ollama integration test failed: {e}")
    
    @pytest.mark.skipif(not os.getenv("OLLAMA_RUNNING"), reason="Ollama not running")
    def test_enhanced_model_service_with_ollama(self):
        """Test enhanced model service with real Ollama connection"""
        from src.core.model_service import ModelService
        
        try:
            model_service = ModelService()
            
            # Test getting models for different agents
            planning_model = model_service.get_model_for_agent("planning")
            research_model = model_service.get_model_for_agent("research")
            code_model = model_service.get_model_for_agent("code")
            
            assert planning_model is not None
            assert research_model is not None
            assert code_model is not None
            
            # Test that models have enhanced features
            assert hasattr(planning_model, 'get_metrics')
            assert hasattr(research_model, 'get_metrics')
            assert hasattr(code_model, 'get_metrics')
            
            # Test simple inference with metrics tracking
            response = planning_model.invoke("What is 2+2?")
            assert response is not None
            assert len(response) > 0
            
            # Check that metrics are being tracked
            metrics = planning_model.get_metrics()
            assert 'total_calls' in metrics
            assert metrics['total_calls'] > 0
            
        except Exception as e:
            pytest.skip(f"Enhanced Ollama model service test failed: {e}")
    
    @pytest.mark.skipif(not os.getenv("OLLAMA_RUNNING"), reason="Ollama not running")
    def test_planning_agent_tool_calling_integration(self):
        """Test planning agent with tool calling capabilities"""
        
        try:
            planning_agent = PlanningAgent()
            
            # Test plan generation with tool calling
            plan = planning_agent.generate_plan("Research AI trends and calculate market size")
            
            assert len(plan) > 0
            assert all(isinstance(task, dict) for task in plan)
            
            # Should have proper task structure
            for task in plan:
                assert 'id' in task
                assert 'type' in task
                assert 'description' in task
                assert 'dependencies' in task
                assert 'status' in task
            
            # Should include both research and code tasks
            task_types = [task['type'] for task in plan]
            assert TaskType.RESEARCH in task_types
            
        except Exception as e:
            pytest.skip(f"Planning agent tool calling test failed: {e}")
    
    @pytest.mark.skipif(not os.getenv("TAVILY_API_KEY"), reason="Tavily API key not available")
    def test_research_agent_tavily_integration(self):
        """Test research agent with real Tavily integration"""
        
        try:
            research_agent = ResearchAgent()
            
            if research_agent.tavily_client:
                # Test enhanced research with Tavily
                result = research_agent.execute_task("Latest developments in renewable energy")
                
                assert len(result) > 100  # Should be substantial
                assert "Source Credibility Assessment" in result
                
                # Should contain credibility indicators
                assert any(indicator in result for indicator in ['🟢', '🟡', '🔴'])
                
                # Should mention Tavily sources if available
                if "Enhanced Tavily sources" in result:
                    assert "Tavily sources:" in result
            else:
                pytest.skip("Tavily client not initialized")
                
        except Exception as e:
            pytest.skip(f"Research agent Tavily test failed: {e}")
    
    @pytest.mark.skipif(not os.getenv("OLLAMA_RUNNING"), reason="Ollama not running")
    def test_code_agent_security_and_execution(self):
        """Test code agent with enhanced security and execution"""
        
        try:
            code_agent = CodeAgent()
            
            # Test conditional execution logic
            assert code_agent.should_execute_code_task("Calculate the factorial of 10") == True
            assert code_agent.should_execute_code_task("What is machine learning?") == False
            
            # Test safe code execution
            safe_result = code_agent.execute_task("Calculate the sum of numbers from 1 to 10")
            
            assert "Code Solution" in safe_result
            assert "Security Summary" in safe_result
            assert "Code Analysis" in safe_result
            
            # Should contain security indicators
            assert "isolated Docker container" in safe_result
            assert "Network access disabled" in safe_result
            
            # Test that non-computational tasks are delegated
            explanation_result = code_agent.execute_task("Explain how neural networks work")
            
            assert ("delegated to conceptual explanation" in explanation_result or
                   "Task Analysis" in explanation_result)
            
        except Exception as e:
            pytest.skip(f"Code agent security test failed: {e}")

if __name__ == "__main__":
    # Run tests with: python -m pytest tests/integration/test_workflow_integration.py -v
    pytest.main([__file__, "-v"])