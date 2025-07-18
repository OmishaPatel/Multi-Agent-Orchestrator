import pytest
from unittest.mock import Mock, patch


class TestWorkflowIntegration:
    
    @pytest.mark.integration
    def test_state_and_code_interpreter_integration(self, sample_agent_state):
        try:
            from graph.state import StateManager
            from tools.code_interpreter import code_interpreter_tool
            
            # Create a workflow state
            state = sample_agent_state.copy()
            
            # Add a code task
            code_task = {
                'id': 3,
                'type': 'code',
                'description': 'Execute Python calculation',
                'dependencies': [],
                'status': 'pending',
                'result': None
            }
            state['plan'].append(code_task)
            
            # Simulate executing the code task
            code_to_execute = "result = 2 + 2\nprint(f'Result: {result}')"
            execution_result = code_interpreter_tool.run(code_to_execute)
            
            # Update state with result
            state['task_results'][3] = execution_result
            state['plan'][2]['status'] = 'completed'
            state['plan'][2]['result'] = execution_result
            
            # Verify integration
            assert StateManager.validate_state(state)
            assert "Result: 4" in execution_result
            assert state['task_results'][3] == execution_result
            
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
    
    @pytest.mark.integration
    def test_human_approval_workflow(self, sample_agent_state):
        try:
            from graph.state import StateManager
            
            state = sample_agent_state.copy()
            
            # Initial state should need approval
            assert StateManager.needs_human_approval(state)
            assert state['human_approval_status'] == 'pending'
            
            # Simulate rejection with feedback
            rejected_state = StateManager.update_approval_status(
                state, 'rejected', 'Please add more research tasks'
            )
            
            assert rejected_state['human_approval_status'] == 'rejected'
            assert rejected_state['user_feedback'] == 'Please add more research tasks'
            
            # Simulate plan modification based on feedback
            # (This would normally be done by a planning agent)
            modified_state = rejected_state.copy()
            research_task = {
                'id': 10,
                'type': 'research',
                'description': 'Additional research based on feedback',
                'dependencies': [],
                'status': 'pending',
                'result': None
            }
            modified_state['plan'].append(research_task)
            modified_state['human_approval_status'] = 'pending'  # Reset for re-approval
            modified_state['user_feedback'] = None
            
            # Simulate approval
            approved_state = StateManager.update_approval_status(
                modified_state, 'approved'
            )
            
            assert approved_state['human_approval_status'] == 'approved'
            assert not StateManager.needs_human_approval(approved_state)
            
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_complete_workflow_simulation(self):
        try:
            from graph.state import StateManager
            
            # Step 1: Initialize workflow
            state = StateManager.create_initial_state(
                "Calculate statistics for a dataset"
            )
            
            # Step 2: Create plan (normally done by planning agent)
            plan = [
                {
                    'id': 1,
                    'type': 'research',
                    'description': 'Research statistical methods',
                    'dependencies': [],
                    'status': 'pending',
                    'result': None
                },
                {
                    'id': 2,
                    'type': 'code',
                    'description': 'Generate sample dataset',
                    'dependencies': [1],
                    'status': 'pending',
                    'result': None
                },
                {
                    'id': 3,
                    'type': 'calculation',
                    'description': 'Calculate mean and standard deviation',
                    'dependencies': [2],
                    'status': 'pending',
                    'result': None
                },
                {
                    'id': 4,
                    'type': 'summary',
                    'description': 'Summarize results',
                    'dependencies': [3],
                    'status': 'pending',
                    'result': None
                }
            ]
            state['plan'] = plan
            
            # Step 3: Human approval
            assert StateManager.needs_human_approval(state)
            approved_state = StateManager.update_approval_status(state, 'approved')
            
            # Step 4: Execute tasks (simulate)
            current_state = approved_state.copy()
            
            # Execute task 1 (research)
            current_state['plan'][0]['status'] = 'completed'
            current_state['plan'][0]['result'] = 'Statistical methods researched'
            current_state['task_results'][1] = 'Statistical methods researched'
            
            # Execute task 2 (code)
            current_state['plan'][1]['status'] = 'completed'
            current_state['plan'][1]['result'] = 'Dataset: [1,2,3,4,5]'
            current_state['task_results'][2] = 'Dataset: [1,2,3,4,5]'
            
            # Execute task 3 (calculation)
            current_state['plan'][2]['status'] = 'completed'
            current_state['plan'][2]['result'] = 'Mean: 3.0, StdDev: 1.58'
            current_state['task_results'][3] = 'Mean: 3.0, StdDev: 1.58'
            
            # Execute task 4 (summary)
            current_state['plan'][3]['status'] = 'completed'
            current_state['plan'][3]['result'] = 'Analysis complete'
            current_state['task_results'][4] = 'Analysis complete'
            
            # Step 5: Generate final report
            final_report = "Workflow completed successfully. Dataset analyzed with mean=3.0 and standard deviation=1.58"
            final_state = StateManager.set_final_report(current_state, final_report)
            
            # Step 6: Verify completion
            assert StateManager.is_workflow_complete(final_state)
            assert StateManager.calculate_progress(final_state) == 1.0
            assert final_state['final_report'] == final_report
            assert StateManager.validate_state(final_state)
            
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")


class TestErrorHandlingIntegration:
    
    @pytest.mark.integration
    def test_state_validation_with_code_execution_errors(self):
        try:
            from graph.state import StateManager
            from tools.code_interpreter import code_interpreter_tool
            
            state = StateManager.create_initial_state("Test error handling")
            
            # Add a task that will fail
            failing_task = {
                'id': 1,
                'type': 'code',
                'description': 'Execute failing code',
                'dependencies': [],
                'status': 'pending',
                'result': None
            }
            state['plan'] = [failing_task]
            
            # Execute failing code
            failing_code = "print(undefined_variable)"
            result = code_interpreter_tool.run(failing_code)
            
            # Update state with error result
            state['plan'][0]['status'] = 'failed'
            state['plan'][0]['result'] = result
            state['task_results'][1] = result
            
            # State should still be valid even with failed tasks
            assert StateManager.validate_state(state)
            assert "error" in result.lower() or "undefined" in result.lower()
            
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")


# Fixtures specific to integration tests
@pytest.fixture
def complex_workflow_state():
    try:
        from graph.state import StateManager
        
        state = StateManager.create_initial_state("Complex workflow test")
        
        # Create a complex plan with multiple dependencies
        complex_plan = [
            {
                'id': 1,
                'type': 'research',
                'description': 'Initial research',
                'dependencies': [],
                'status': 'completed',
                'result': 'Research completed'
            },
            {
                'id': 2,
                'type': 'research',
                'description': 'Secondary research',
                'dependencies': [],
                'status': 'completed',
                'result': 'Secondary research completed'
            },
            {
                'id': 3,
                'type': 'analysis',
                'description': 'Analyze research findings',
                'dependencies': [1, 2],
                'status': 'pending',
                'result': None
            },
            {
                'id': 4,
                'type': 'code',
                'description': 'Implement solution',
                'dependencies': [3],
                'status': 'pending',
                'result': None
            },
            {
                'id': 5,
                'type': 'summary',
                'description': 'Create final summary',
                'dependencies': [4],
                'status': 'pending',
                'result': None
            }
        ]
        
        state['plan'] = complex_plan
        state['task_results'] = {1: 'Research completed', 2: 'Secondary research completed'}
        state['next_task_id'] = 3
        
        return state
        
    except ImportError:
        pytest.skip("StateManager not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])