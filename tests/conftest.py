"""
Shared pytest configuration and fixtures for all tests.
"""
import pytest
import sys
import os
from pathlib import Path

# Add src to Python path for imports
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

@pytest.fixture(scope="session")
def project_root_path():
    """Provide the project root path."""
    return project_root

@pytest.fixture(scope="session")
def src_path():
    """Provide the src directory path."""
    return project_root / "src"

@pytest.fixture
def sample_agent_state():
    """Provide a sample AgentState for testing."""
    from graph.state import AgentState, SubTask
    
    return AgentState(
        user_request="Test request",
        plan=[
            SubTask(
                id=1,
                type="research",
                description="Test task 1",
                dependencies=[],
                status="pending",
                result=None
            ),
            SubTask(
                id=2,
                type="code",
                description="Test task 2", 
                dependencies=[1],
                status="pending",
                result=None
            )
        ],
        task_results={},
        next_task_id=1,
        messages=[],
        human_approval_status="pending",
        user_feedback=None,
        final_report=None
    )

@pytest.fixture
def mock_docker_client():
    """Mock Docker client for testing without Docker dependency."""
    from unittest.mock import Mock
    
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_client.containers.run.return_value.logs.return_value = b"Test output"
    
    return mock_client