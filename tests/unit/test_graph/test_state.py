import pytest
from typing import Dict, Any
from pydantic import ValidationError


class TestAgentState:
    
    def test_agent_state_creation(self, sample_agent_state):
        """Test creating a basic AgentState."""
        state = sample_agent_state
        
        assert state['user_request'] == "Test request"
        assert len(state['plan']) == 2
        assert state['human_approval_status'] == "pending"
        assert state['user_feedback'] is None
        assert state['final_report'] is None
    
    def test_agent_state_fields(self, sample_agent_state):
        state = sample_agent_state
        
        required_fields = [
            'user_request', 'plan', 'task_results', 'next_task_id', 
            'messages', 'human_approval_status', 'user_feedback', 'final_report'
        ]
        
        for field in required_fields:
            assert field in state, f"Required field '{field}' missing from state"


class TestStateManager:    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up StateManager for testing."""
        try:
            from graph.state import StateManager
            self.state_manager = StateManager
        except ImportError:
            pytest.skip("StateManager not available")
    
    def test_create_initial_state(self):
        
        state = self.state_manager.create_initial_state("Test request")
        
        assert state['user_request'] == "Test request"
        assert state['plan'] == []
        assert state['task_results'] == {}
        assert state['next_task_id'] is None
        assert state['human_approval_status'] == 'pending'
        assert state['user_feedback'] is None
        assert state['final_report'] is None
    
    def test_update_approval_status_approved(self):
        
        initial_state = self.state_manager.create_initial_state("Test")
        
        updated_state = self.state_manager.update_approval_status(
            initial_state, 'approved'
        )
        
        assert updated_state['human_approval_status'] == 'approved'
        assert updated_state['user_feedback'] is None
    
    def test_update_approval_status_rejected_with_feedback(self):
        initial_state = self.state_manager.create_initial_state("Test")
        
        updated_state = self.state_manager.update_approval_status(
            initial_state, 'rejected', 'Please add more detail'
        )
        
        assert updated_state['human_approval_status'] == 'rejected'
        assert updated_state['user_feedback'] == 'Please add more detail'
    
    def test_update_approval_status_rejected_without_feedback_raises_error(self):
        initial_state = self.state_manager.create_initial_state("Test")
        
        with pytest.raises(ValueError, match="Feedback is required"):
            self.state_manager.update_approval_status(initial_state, 'rejected')
    
    def test_set_final_report(self):
        initial_state = self.state_manager.create_initial_state("Test")
        
        updated_state = self.state_manager.set_final_report(
            initial_state, "Final workflow report"
        )
        
        assert updated_state['final_report'] == "Final workflow report"
    
    def test_get_pending_tasks(self, sample_agent_state):
        pending_tasks = self.state_manager.get_pending_tasks(sample_agent_state)
        
        assert len(pending_tasks) == 2
        assert all(task['status'] == 'pending' for task in pending_tasks)
    
    def test_get_completed_tasks(self, sample_agent_state):
        # Modify sample state to have completed tasks
        state = sample_agent_state.copy()
        state['plan'][0]['status'] = 'completed'
        
        completed_tasks = self.state_manager.get_completed_tasks(state)
        
        assert len(completed_tasks) == 1
        assert completed_tasks[0]['status'] == 'completed'
    
    def test_calculate_progress_empty_plan(self):
        state = self.state_manager.create_initial_state("Test")
        progress = self.state_manager.calculate_progress(state)
        
        assert progress == 0.0
    
    def test_calculate_progress_partial_completion(self, sample_agent_state):
        state = sample_agent_state.copy()
        state['plan'][0]['status'] = 'completed'
        
        progress = self.state_manager.calculate_progress(state)
        
        assert progress == 0.5  # 1 out of 2 tasks completed
    
    def test_calculate_progress_full_completion(self, sample_agent_state):
        state = sample_agent_state.copy()
        for task in state['plan']:
            task['status'] = 'completed'
        
        progress = self.state_manager.calculate_progress(state)
        
        assert progress == 1.0
    
    def test_is_workflow_complete_false(self, sample_agent_state):
        assert not self.state_manager.is_workflow_complete(sample_agent_state)
    
    def test_is_workflow_complete_true(self, sample_agent_state):
        state = sample_agent_state.copy()
        for task in state['plan']:
            task['status'] = 'completed'
        
        assert self.state_manager.is_workflow_complete(state)
    
    def test_needs_human_approval_true(self, sample_agent_state):
        assert self.state_manager.needs_human_approval(sample_agent_state)
    
    def test_needs_human_approval_false_approved(self, sample_agent_state):
        state = sample_agent_state.copy()
        state['human_approval_status'] = 'approved'
        
        assert not self.state_manager.needs_human_approval(state)
    
    def test_needs_human_approval_false_empty_plan(self):
        state = self.state_manager.create_initial_state("Test")
        
        assert not self.state_manager.needs_human_approval(state)


class TestAgentStateValidator:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up validator for testing."""
        try:
            from graph.state import AgentStateValidator
            self.validator = AgentStateValidator
        except ImportError:
            pytest.skip("AgentStateValidator not available")
    
    def test_valid_state_validation(self):
        valid_data = {
            'user_request': 'Test request',
            'plan': [],
            'task_results': {},
            'next_task_id': None,
            'human_approval_status': 'pending',
            'user_feedback': None,
            'final_report': None
        }
        
        validator = self.validator(**valid_data)
        assert validator.user_request == 'Test request'
        assert validator.human_approval_status == 'pending'
    
    def test_invalid_approval_status(self):
        invalid_data = {
            'user_request': 'Test request',
            'human_approval_status': 'invalid_status'
        }
        
        with pytest.raises(ValidationError):
            self.validator(**invalid_data)
    
    def test_rejected_without_feedback_validation_error(self):
        invalid_data = {
            'user_request': 'Test request',
            'human_approval_status': 'rejected',
            'user_feedback': None
        }
        
        with pytest.raises(ValidationError, match="User feedback is required"):
            self.validator(**invalid_data)
    
    def test_rejected_with_feedback_validation_success(self):
        valid_data = {
            'user_request': 'Test request',
            'human_approval_status': 'rejected',
            'user_feedback': 'Please improve the plan'
        }
        
        validator = self.validator(**valid_data)
        assert validator.human_approval_status == 'rejected'
        assert validator.user_feedback == 'Please improve the plan'
    
    def test_plan_validation_invalid_task_type(self):
        invalid_data = {
            'user_request': 'Test request',
            'plan': [{
                'id': 1,
                'type': 'invalid_type',
                'description': 'Test task',
                'dependencies': [],
                'status': 'pending',
                'result': None
            }]
        }
        
        with pytest.raises(ValidationError, match="Invalid task type"):
            self.validator(**invalid_data)
    
    def test_plan_validation_invalid_status(self):
        invalid_data = {
            'user_request': 'Test request',
            'plan': [{
                'id': 1,
                'type': 'research',
                'description': 'Test task',
                'dependencies': [],
                'status': 'invalid_status',
                'result': None
            }]
        }
        
        with pytest.raises(ValidationError, match="Invalid task status"):
            self.validator(**invalid_data)
    
    def test_plan_validation_invalid_dependency(self):
        invalid_data = {
            'user_request': 'Test request',
            'plan': [{
                'id': 1,
                'type': 'research',
                'description': 'Test task',
                'dependencies': [999],  # Non-existent dependency
                'status': 'pending',
                'result': None
            }]
        }
        
        with pytest.raises(ValidationError, match="invalid dependency"):
            self.validator(**invalid_data)
    
    def test_next_task_id_validation_invalid(self):
        invalid_data = {
            'user_request': 'Test request',
            'plan': [{
                'id': 1,
                'type': 'research',
                'description': 'Test task',
                'dependencies': [],
                'status': 'pending'
            }],
            'next_task_id': 999  # Non-existent task ID
        }
        
        with pytest.raises(ValidationError, match="does not exist in plan"):
            self.validator(**invalid_data)


class TestStateConstants:
    
    def test_approval_status_constants(self):
        try:
            from graph.state import ApprovalStatus
            
            assert ApprovalStatus.PENDING == 'pending'
            assert ApprovalStatus.APPROVED == 'approved'
            assert ApprovalStatus.REJECTED == 'rejected'
        except ImportError:
            pytest.skip("ApprovalStatus constants not available")
    
    def test_task_status_constants(self):
        try:
            from graph.state import TaskStatus
            
            assert TaskStatus.PENDING == 'pending'
            assert TaskStatus.IN_PROGRESS == 'in_progress'
            assert TaskStatus.COMPLETED == 'completed'
            assert TaskStatus.FAILED == 'failed'
        except ImportError:
            pytest.skip("TaskStatus constants not available")
    
    def test_task_type_constants(self):
        try:
            from graph.state import TaskType
            
            assert TaskType.RESEARCH == 'research'
            assert TaskType.CODE == 'code'
            assert TaskType.ANALYSIS == 'analysis'
            assert TaskType.SUMMARY == 'summary'
            assert TaskType.CALCULATION == 'calculation'
        except ImportError:
            pytest.skip("TaskType constants not available")


# Performance tests
class TestStatePerformance:
    
    @pytest.mark.slow
    def test_large_plan_validation_performance(self):
        try:
            from graph.state import StateManager
            
            # Create state with many tasks
            state = StateManager.create_initial_state("Large test")
            
            # Add 1000 tasks
            large_plan = []
            for i in range(1000):
                task = {
                    'id': i,
                    'type': 'research',
                    'description': f'Task {i}',
                    'dependencies': [i-1] if i > 0 else [],
                    'status': 'pending',
                    'result': None
                }
                large_plan.append(task)
            
            state['plan'] = large_plan
            
            # Validation should complete in reasonable time
            import time
            start = time.time()
            is_valid = StateManager.validate_state(state)
            end = time.time()
            
            assert is_valid
            assert end - start < 1.0  # Should complete within 1 second
            
        except ImportError:
            pytest.skip("StateManager not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])