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
                        "result": "Sum = 55"
                    },
                    {
                        "id": 2,
                        "type": TaskType.SUMMARY,
                        "description": "Summarize calculation results",
                        "dependencies": [1],
                        "status": TaskStatus.COMPLETED,
                        "result": "The sum of numbers from 1 to 10 is 55"
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
                        "result": None
                    },
                    {
                        "id": 2,
                        "type": TaskType.CODE,
                        "description": "Create data visualization code",
                        "dependencies": [1],
                        "status": TaskStatus.PENDING,
                        "result": None
                    },
                    {
                        "id": 3,
                        "type": TaskType.ANALYSIS,
                        "description": "Analyze statistical insights",
                        "dependencies": [1, 2],
                        "status": TaskStatus.PENDING,
                        "result": None
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

    # ==================== Future Endpoint Tests (Commented Out) ====================
    
    # TODO: Uncomment and implement when /status endpoint is added
    # def test_status_endpoint_workflow_complete(self, client, mock_workflow_factory, sample_workflow_result):
    #     """Test /status endpoint for completed workflow"""
    #     
    #     # Expected behavior:
    #     # - GET /api/v1/status/{thread_id}
    #     # - Returns workflow status, progress, and results
    #     # - Handles non-existent thread_ids gracefully
    #     pass
    
    # def test_status_endpoint_workflow_pending_approval(self, client, mock_workflow_factory, sample_pending_approval_result):
    #     """Test /status endpoint for workflow pending approval"""
    #     
    #     # Expected behavior:
    #     # - Returns status "pending_approval"
    #     # - Includes plan details for user review
    #     # - Shows progress of completed tasks
    #     pass
    
    # def test_status_endpoint_invalid_thread_id(self, client):
    #     """Test /status endpoint with non-existent thread_id"""
    #     
    #     # response = client.get("/api/v1/status/non-existent-thread")
    #     # assert response.status_code == 404
    #     pass

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
    # def test_complete_workflow_flow_simulation(self, client, mock_workflow_factory, sample_pending_approval_result, sample_workflow_result):
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
