import pytest
import asyncio
import time
import uuid
import json
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any

from src.main import app
from src.core.workflow_factory import WorkflowFactory
from src.graph.state import AgentState, TaskType, TaskStatus, ApprovalStatus

class TestAPIIntegration:
    """
    Integration tests for the Clarity.ai API endpoints.
    
    Currently covers:
    - /run endpoint functionality
    - Health check endpoint
    - Error handling and edge cases
    
    Future endpoints (commented out):
    - /status endpoint
    - /approve endpoint
    """
    
    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_workflow_factory(self):
        """Mock WorkflowFactory for controlled testing"""
        mock_factory = Mock(spec=WorkflowFactory)
        mock_factory.checkpointing_enabled = True
        mock_factory.checkpointing_type = "hybrid"
        mock_factory.redis_state_manager = Mock()
        return mock_factory
    
    @pytest.fixture
    def sample_requests(self):
        """Load sample requests from fixtures"""
        fixtures_path = Path(__file__).parent.parent / "fixtures" / "sample_requests.json"
        with open(fixtures_path, 'r') as f:
            return json.load(f)
    
    @pytest.fixture
    def mock_responses(self):
        """Load mock responses from fixtures"""
        fixtures_path = Path(__file__).parent.parent / "fixtures" / "mock_responses.json"
        with open(fixtures_path, 'r') as f:
            return json.load(f)
    
    @pytest.fixture
    def sample_workflow_result(self, sample_requests):
        """Sample workflow result for testing"""
        return {
            "thread_id": "test-thread-123",
            "result": {
                "user_request": sample_requests["simple_request"]["user_request"],
                "plan": [
                    {
                        "id": 1,
                        "type": TaskType.CALCULATION,
                        "description": "Calculate sum of numbers 1 to 10",
                        "dependencies": [],
                        "status": TaskStatus.COMPLETED,
                        "result": "Sum = 55",
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    },
                    {
                        "id": 2,
                        "type": TaskType.SUMMARY,
                        "description": "Summarize calculation results",
                        "dependencies": [1],
                        "status": TaskStatus.COMPLETED,
                        "result": "The sum of numbers from 1 to 10 is 55",
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    }
                ],
                "task_results": {
                    1: "Sum = 55",
                    2: "The sum of numbers from 1 to 10 is 55"
                },
                "next_task_id": None,
                "messages": ["Workflow completed successfully"],
                "human_approval_status": ApprovalStatus.APPROVED,
                "user_feedback": None,
                "final_report": "Calculation completed: The sum of numbers from 1 to 10 is 55"
            }
        }
    
    @pytest.fixture
    def sample_pending_approval_result(self, sample_requests):
        """Sample workflow result pending approval"""
        return {
            "thread_id": "test-thread-pending",
            "result": {
                "user_request": sample_requests["complex_request"]["user_request"],
                "plan": [
                    {
                        "id": 1,
                        "type": TaskType.RESEARCH,
                        "description": "Research dataset analysis techniques",
                        "dependencies": [],
                        "status": TaskStatus.PENDING,
                        "result": None,
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    },
                    {
                        "id": 2,
                        "type": TaskType.CODE,
                        "description": "Create data visualization code",
                        "dependencies": [1],
                        "status": TaskStatus.PENDING,
                        "result": None,
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    },
                    {
                        "id": 3,
                        "type": TaskType.ANALYSIS,
                        "description": "Analyze statistical insights",
                        "dependencies": [1, 2],
                        "status": TaskStatus.PENDING,
                        "result": None,
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    }
                ],
                "task_results": {},
                "next_task_id": 1,
                "messages": ["Plan generated, awaiting approval"],
                "human_approval_status": ApprovalStatus.PENDING,
                "user_feedback": None,
                "final_report": None
            }
        }

    @pytest.fixture
    def sample_in_progress_result(self, sample_requests):
        """Sample workflow result with tasks in progress"""
        return {
            "thread_id": "test-thread-progress",
            "result": {
                "user_request": sample_requests["complex_request"]["user_request"],
                "plan": [
                    {
                        "id": 1,
                        "type": TaskType.RESEARCH,
                        "description": "Research dataset analysis techniques",
                        "dependencies": [],
                        "status": TaskStatus.COMPLETED,
                        "result": "Research completed successfully",
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    },
                    {
                        "id": 2,
                        "type": TaskType.CODE,
                        "description": "Create data visualization code",
                        "dependencies": [1],
                        "status": TaskStatus.IN_PROGRESS,
                        "result": None,
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    },
                    {
                        "id": 3,
                        "type": TaskType.ANALYSIS,
                        "description": "Analyze statistical insights",
                        "dependencies": [1, 2],
                        "status": TaskStatus.PENDING,
                        "result": None,
                        "started_at": "2024-01-15T10:35:00Z",
                        "completed_at": "2024-01-15T10:40:00Z"

                    }
                ],
                "task_results": {
                    1: "Research completed successfully"
                },
                "next_task_id": 2,
                "messages": ["Plan approved", "Task 1 completed", "Task 2 in progress"],
                "human_approval_status": ApprovalStatus.APPROVED,
                "user_feedback": None,
                "final_report": None
            }
        }

    # ==================== /run Endpoint Tests ====================
    
    @patch('src.api.routes.workflow.execute_workflow_background')
    def test_run_endpoint_success(self, mock_bg_task, client, mock_workflow_factory, sample_workflow_result):
        """Test successful workflow initiation"""
        
        # Mock background task to do nothing
        mock_bg_task.return_value = None
        
        with patch('src.api.routes.workflow.get_workflow_factory', return_value=mock_workflow_factory):
            mock_workflow_factory.start_new_workflow.return_value = sample_workflow_result
            
            response = client.post(
                "/api/v1/run",
                json={"user_request": "Test request for workflow execution"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "thread_id" in data
            assert data["status"] == "initiated"
            assert "Workflow started successfully" in data["message"]
            assert "created_at" in data
            
            # Verify thread_id is valid UUID
            uuid.UUID(data["thread_id"])
            
            # Verify background task was called
            mock_bg_task.assert_called_once()
    
    @patch('src.api.routes.workflow.execute_workflow_background')
    def test_run_endpoint_with_sample_requests(self, mock_bg_task, client, mock_workflow_factory, sample_requests, sample_workflow_result):
        """Test /run endpoint with various sample requests from fixtures"""
        
        # Mock background task to do nothing
        mock_bg_task.return_value = None
        
        with patch('src.api.routes.workflow.get_workflow_factory', return_value=mock_workflow_factory):
            mock_workflow_factory.start_new_workflow.return_value = sample_workflow_result
            
            for request_name, request_data in sample_requests.items():
                response = client.post(
                    "/api/v1/run",
                    json={"user_request": request_data["user_request"]}
                )
                
                assert response.status_code == 200, f"Failed for request: {request_name}"
                data = response.json()
                assert "thread_id" in data
                assert data["status"] == "initiated"
    
    def test_run_endpoint_empty_request(self, client):
        """Test /run endpoint with empty request"""
        
        response = client.post(
            "/api/v1/run",
            json={"user_request": ""}
        )
        
        assert response.status_code == 422
    
    def test_run_endpoint_whitespace_only_request(self, client):
        """Test /run endpoint with whitespace-only request"""
        
        response = client.post(
            "/api/v1/run",
            json={"user_request": "   \n\t   "}
        )
        
        assert response.status_code == 400
    
    def test_run_endpoint_missing_request_field(self, client):
        """Test /run endpoint with missing user_request field"""
        
        response = client.post(
            "/api/v1/run",
            json={}
        )
        
        assert response.status_code == 422  # Pydantic validation error
    
    @patch('src.api.routes.workflow.execute_workflow_background')
    def test_run_endpoint_workflow_factory_error(self, mock_bg_task, client):
        """Test /run endpoint when background workflow execution fails"""
        
        # Mock background task to simulate a workflow factory error
        mock_bg_task.side_effect = Exception("Workflow factory error")
        
        # The background task failure should cause the request to fail
        with pytest.raises(Exception, match="Workflow factory error"):
            response = client.post(
                "/api/v1/run",
                json={"user_request": "Test request"}
            )
        
        # Verify background task was called and failed
        mock_bg_task.assert_called_once()
     
    # ==================== Error Handling and Edge Cases ====================
    
    @patch('src.api.routes.workflow.execute_workflow_background')
    def test_concurrent_workflow_requests(self, mock_bg_task, client, mock_workflow_factory, sample_workflow_result):
        """Test handling multiple concurrent workflow requests"""
        
        # Mock background task to do nothing
        mock_bg_task.return_value = None
        
        with patch('src.api.routes.workflow.get_workflow_factory', return_value=mock_workflow_factory):
            mock_workflow_factory.start_new_workflow.return_value = sample_workflow_result
            
            # Make multiple concurrent requests
            responses = []
            for i in range(5):
                response = client.post(
                    "/api/v1/run",
                    json={"user_request": f"Concurrent test request {i}"}
                )
                responses.append(response)
            
            # All should succeed with unique thread IDs
            thread_ids = set()
            for response in responses:
                assert response.status_code == 200
                thread_id = response.json()["thread_id"]
                assert thread_id not in thread_ids
                thread_ids.add(thread_id)
            
            # Verify background tasks were called
            assert mock_bg_task.call_count == 5
    
    @patch('src.api.routes.workflow.execute_workflow_background')
    def test_very_long_request(self, mock_bg_task, client):
        """Test handling of very long user requests"""
        
        # Mock background task to do nothing
        mock_bg_task.return_value = None
        
        # Test with request at the limit (5000 chars)
        long_request = "A" * 5000
        response = client.post(
            "/api/v1/run",
            json={"user_request": long_request}
        )
        
        # Should succeed (assuming no additional length validation in endpoint)
        assert response.status_code in [200, 422]  # 422 if Pydantic validation fails
        
        # Test with request over the limit
        too_long_request = "A" * 5001
        response = client.post(
            "/api/v1/run",
            json={"user_request": too_long_request}
        )
        
        # Should fail validation
        assert response.status_code == 422
    
    def test_invalid_json_request(self, client):
        """Test handling of invalid JSON in request"""
        
        response = client.post(
            "/api/v1/run",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422

 # ==================== /status Endpoint Tests ====================
    
    def test_status_endpoint_workflow_completed(self, client, mock_workflow_factory, sample_workflow_result):
        """Test /status endpoint for completed workflow"""
        
        thread_id = "test-thread-123"
        
        # Mock workflow factory to return completed workflow status
        mock_status_data = {
            "thread_id": thread_id,
            "status": "completed",
            "user_request": sample_workflow_result["result"]["user_request"],
            "plan": sample_workflow_result["result"]["plan"],
            "task_results": sample_workflow_result["result"]["task_results"],
            "next_task_id": sample_workflow_result["result"]["next_task_id"],
            "messages": sample_workflow_result["result"]["messages"],
            "human_approval_status": sample_workflow_result["result"]["human_approval_status"],
            "user_feedback": sample_workflow_result["result"]["user_feedback"],
            "final_report": sample_workflow_result["result"]["final_report"]
        }
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = mock_status_data
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify basic response structure
            assert data["thread_id"] == thread_id
            assert data["status"] == "completed"
            assert data["user_request"] == sample_workflow_result["result"]["user_request"]
            assert data["human_approval_status"] == "approved"
            assert data["final_report"] is not None
            assert data["checkpointing_type"] == "hybrid"
            
            # Verify progress metrics
            progress = data["progress"]
            assert progress["total_tasks"] == 2
            assert progress["completed_tasks"] == 2
            assert progress["failed_tasks"] == 0
            assert progress["completion_percentage"] == 100.0
            
            # Verify task information
            tasks = data["tasks"]
            assert len(tasks) == 2
            assert all("id" in task for task in tasks)
            assert all("type" in task for task in tasks)
            assert all("status" in task for task in tasks)
            
            # Verify timestamps
            assert "last_updated" in data
    
    def test_status_endpoint_workflow_pending_approval(self, client, mock_workflow_factory, sample_pending_approval_result):
        """Test /status endpoint for workflow pending approval"""
        
        thread_id = "test-thread-pending"
        
        # Mock workflow factory to return pending approval status
        mock_status_data = {
            "thread_id": thread_id,
            "status": "pending_approval",
            "user_request": sample_pending_approval_result["result"]["user_request"],
            "plan": sample_pending_approval_result["result"]["plan"],
            "task_results": sample_pending_approval_result["result"]["task_results"],
            "next_task_id": sample_pending_approval_result["result"]["next_task_id"],
            "messages": sample_pending_approval_result["result"]["messages"],
            "human_approval_status": sample_pending_approval_result["result"]["human_approval_status"],
            "user_feedback": sample_pending_approval_result["result"]["user_feedback"],
            "final_report": sample_pending_approval_result["result"]["final_report"]
        }
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = mock_status_data
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify pending approval status
            assert data["thread_id"] == thread_id
            assert data["status"] == "pending_approval"
            assert data["human_approval_status"] == "pending"
            assert data["final_report"] is None
            
            # Verify progress metrics for pending tasks
            progress = data["progress"]
            assert progress["total_tasks"] == 3
            assert progress["completed_tasks"] == 0
            assert progress["pending_tasks"] == 3
            assert progress["completion_percentage"] == 0.0
            
            # Verify all tasks are pending
            tasks = data["tasks"]
            assert len(tasks) == 3
            assert all(task["status"] == "pending" for task in tasks)
    
    def test_status_endpoint_workflow_in_progress(self, client, mock_workflow_factory, sample_in_progress_result):
        """Test /status endpoint for workflow with tasks in progress"""
        
        thread_id = "test-thread-progress"
        
        # Mock workflow factory to return in-progress status
        mock_status_data = {
            "thread_id": thread_id,
            "status": "in_progress",
            "user_request": sample_in_progress_result["result"]["user_request"],
            "plan": sample_in_progress_result["result"]["plan"],
            "task_results": sample_in_progress_result["result"]["task_results"],
            "next_task_id": sample_in_progress_result["result"]["next_task_id"],
            "messages": sample_in_progress_result["result"]["messages"],
            "human_approval_status": sample_in_progress_result["result"]["human_approval_status"],
            "user_feedback": sample_in_progress_result["result"]["user_feedback"],
            "final_report": sample_in_progress_result["result"]["final_report"]
        }
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = mock_status_data
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify in-progress status
            assert data["thread_id"] == thread_id
            assert data["status"] == "in_progress"
            assert data["human_approval_status"] == "approved"
            
            # Verify progress metrics
            progress = data["progress"]
            assert progress["total_tasks"] == 3
            assert progress["completed_tasks"] == 1
            assert progress["in_progress_tasks"] == 1
            assert progress["pending_tasks"] == 1
            assert progress["completion_percentage"] == 33.3
            
            # Verify current task identification
            current_task = data["current_task"]
            assert current_task is not None
            assert current_task["id"] == 2
            assert current_task["status"] == "in_progress"
            
            # Verify task status distribution
            tasks = data["tasks"]
            completed_tasks = [t for t in tasks if t["status"] == "completed"]
            in_progress_tasks = [t for t in tasks if t["status"] == "in_progress"]
            pending_tasks = [t for t in tasks if t["status"] == "pending"]
            
            assert len(completed_tasks) == 1
            assert len(in_progress_tasks) == 1
            assert len(pending_tasks) == 1
    
    def test_status_endpoint_invalid_thread_id(self, client, mock_workflow_factory):
        """Test /status endpoint with non-existent thread_id"""
        
        thread_id = "test-non-existent-thread"
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = {"status": "not_found"}
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()
    
    def test_status_endpoint_malformed_thread_id(self, client):
        """Test /status endpoint with malformed thread_id"""
        
        invalid_thread_id = "not-a-uuid"
        
        response = client.get(f"/api/v1/status/{invalid_thread_id}")
        
        assert response.status_code == 400
        data = response.json()
        assert "Invalid thread_id format" in data["detail"]
    
    def test_status_endpoint_workflow_error(self, client, mock_workflow_factory):
        """Test /status endpoint when workflow has error status"""
        
        thread_id = "test-thread-error"
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = {
                "status": "error",
                "error": "Redis connection failed"
            }
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 500
            data = response.json()
            assert "Error retrieving workflow status" in data["detail"]
    
    def test_status_endpoint_different_checkpointing_types(self, client, mock_workflow_factory):
        """Test /status endpoint with different checkpointing configurations"""
        
        thread_id = "test-thread-memory"
        
        # Test with memory checkpointing
        mock_status_data = {
            "thread_id": thread_id,
            "status": "running",
            "checkpointing": "memory",
            "note": "Limited status info available with memory checkpointing"
        }
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = mock_status_data
            mock_factory_instance.checkpointing_type = "memory"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["checkpointing_type"] == "memory"
            assert data["status"] == "planning"  # Default when no plan available
    
    def test_status_endpoint_progress_calculation_edge_cases(self, client, mock_workflow_factory):
        """Test progress calculation with edge cases"""
        
        thread_id = "test-thread-edge"
        
        # Test with empty plan
        mock_status_data = {
            "thread_id": thread_id,
            "status": "planning",
            "user_request": "Test request",
            "plan": [],
            "task_results": {},
            "next_task_id": None,
            "messages": ["Planning in progress"],
            "human_approval_status": "pending",
            "user_feedback": None,
            "final_report": None
        }
        
        # Mock the WorkflowFactory class at the module level where it's imported
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = mock_status_data
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            response = client.get(f"/api/v1/status/{thread_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify empty plan handling
            progress = data["progress"]
            assert progress["total_tasks"] == 0
            assert progress["completion_percentage"] == 0.0
            assert data["current_task"] is None
            assert len(data["tasks"]) == 0

    def test_complete_workflow_status_flow_simulation(self, client, mock_workflow_factory, sample_pending_approval_result, sample_in_progress_result, sample_workflow_result):
        """Test complete workflow flow: run -> status (pending) -> status (in progress) -> status (completed)"""
        
        thread_id = "test-flow-thread"
        
        # Step 1: Start workflow
        with patch('src.api.routes.workflow.execute_workflow_background') as mock_bg_task:
            mock_bg_task.return_value = None
            
            with patch('src.api.routes.workflow.get_workflow_factory', return_value=mock_workflow_factory):
                mock_workflow_factory.start_new_workflow.return_value = {"thread_id": thread_id, "result": {}}
                
                run_response = client.post(
                    "/api/v1/run",
                    json={"user_request": "Test workflow flow"}
                )
                
                assert run_response.status_code == 200
                returned_thread_id = run_response.json()["thread_id"]
        
        # Step 2: Check status - pending approval
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = {
                "thread_id": thread_id,
                "status": "pending_approval",
                **sample_pending_approval_result["result"]
            }
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            status_response = client.get(f"/api/v1/status/{returned_thread_id}")
            
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["status"] == "pending_approval"
            assert status_data["progress"]["completion_percentage"] == 0.0
        
        # Step 3: Check status - in progress (simulating after approval)
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = {
                "thread_id": thread_id,
                "status": "in_progress",
                **sample_in_progress_result["result"]
            }
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            status_response = client.get(f"/api/v1/status/{returned_thread_id}")
            
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["status"] == "in_progress"
            assert status_data["progress"]["completion_percentage"] == 33.3
            assert status_data["current_task"] is not None
        
        # Step 4: Check status - completed
        with patch('src.api.routes.workflow.WorkflowFactory') as mock_factory_class:
            mock_factory_instance = Mock()
            mock_factory_instance.get_workflow_status.return_value = {
                "thread_id": thread_id,
                "status": "completed",
                **sample_workflow_result["result"]
            }
            mock_factory_instance.checkpointing_type = "hybrid"
            mock_factory_class.return_value = mock_factory_instance
            
            status_response = client.get(f"/api/v1/status/{returned_thread_id}")
            
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["status"] == "completed"
            assert status_data["progress"]["completion_percentage"] == 100.0
            assert status_data["final_report"] is not None
 # ==================== Future Endpoint Tests (Commented Out) ====================
    
    # TODO: Uncomment and implement when /approve endpoint is added
    # def test_approve_endpoint_approval_success(self, client, mock_workflow_factory):
    #     """Test /approve endpoint for successful approval"""
    #     
    #     # Expected behavior:
    #     # - POST /api/v1/approve/{thread_id}
    #     # - Body: {"approved": true} or {"approved": false, "feedback": "..."}
    #     # - Resumes workflow execution
    #     # - Returns updated status
    #     pass
    
    # def test_approve_endpoint_rejection_with_feedback(self, client, mock_workflow_factory):
    #     """Test /approve endpoint for rejection with feedback"""
    #     
    #     # Expected behavior:
    #     # - Requires feedback when approved=false
    #     # - Triggers plan regeneration
    #     # - Returns to pending approval state
    #     pass
    
    # def test_approve_endpoint_invalid_thread_id(self, client):
    #     """Test /approve endpoint with non-existent thread_id"""
    #     
    #     # response = client.post("/api/v1/approve/non-existent-thread", json={"approved": true})
    #     # assert response.status_code == 404
    #     pass

    # TODO: Uncomment and implement when both endpoints are ready
    # def test_complete_workflow_flow_with_approval(self, client, mock_workflow_factory, sample_pending_approval_result, sample_workflow_result):
    #     """Test complete workflow flow: run -> status -> approve -> status"""
    #     
    #     # Expected flow:
    #     # 1. POST /run -> get thread_id
    #     # 2. GET /status/{thread_id} -> check pending approval
    #     # 3. POST /approve/{thread_id} -> approve plan
    #     # 4. GET /status/{thread_id} -> check execution progress
    #     # 5. GET /status/{thread_id} -> check final completion
    #     pass
    
    # def test_workflow_rejection_and_regeneration_flow(self, client, mock_workflow_factory):
    #     """Test workflow rejection and plan regeneration flow"""
    #     
    #     # Expected flow:
    #     # 1. POST /run -> get thread_id
    #     # 2. GET /status/{thread_id} -> pending approval
    #     # 3. POST /approve/{thread_id} with rejection and feedback
    #     # 4. GET /status/{thread_id} -> new plan pending approval
    #     # 5. POST /approve/{thread_id} with approval
    #     # 6. GET /status/{thread_id} -> execution in progress
    #     pass
    # ==================== Helper Methods for Future Extensions ====================
    
    def _create_test_workflow(self, client, request_text: str) -> str:
        """
        Helper method to create a test workflow and return thread_id.
        
        Useful for setting up tests for /status and /approve endpoints.
        """
        response = client.post(
            "/api/v1/run",
            json={"user_request": request_text}
        )
        assert response.status_code == 200
        return response.json()["thread_id"]
    
    # def _wait_for_workflow_completion(self, client, thread_id: str, timeout: int = 30) -> Dict[str, Any]:
    #     """
    #     Helper method to wait for workflow completion (for future use).
    #     
    #     This will be useful when implementing /status endpoint tests.
    #     """
    #     start_time = time.time()
    #     while time.time() - start_time < timeout:
    #         # TODO: Replace with actual /status endpoint call when implemented
    #         # response = client.get(f"/api/v1/status/{thread_id}")
    #         # if response.status_code == 200:
    #         #     data = response.json()
    #         #     if data["status"] in ["completed", "failed"]:
    #         #         return data
    #         time.sleep(0.5)
    #     
    #     raise TimeoutError(f"Workflow {thread_id} did not complete within {timeout} seconds")

# ==================== Additional Fixtures for API Testing ====================

@pytest.fixture
def invalid_requests():
    """Invalid user requests for testing"""
    return [
        "",  # Empty
        "   ",  # Whitespace only
        "\n\t\r",  # Various whitespace
    ]

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
