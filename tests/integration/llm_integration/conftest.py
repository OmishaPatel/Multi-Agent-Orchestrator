"""
Conftest for LLM integration tests.
"""
import pytest
import os
import uuid
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

@pytest.fixture(scope="session")
def workflow_factory():
    """Create a WorkflowFactory instance for testing."""
    # Set environment for testing
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["REDIS_ENABLED"] = "true"
    os.environ["ENABLE_CHECKPOINTING"] = "true"
    
    from src.core.workflow_factory import WorkflowFactory
    return WorkflowFactory()

@pytest.fixture
def thread_id():
    """Generate a unique thread ID for testing."""
    return str(uuid.uuid4())

@pytest.fixture
def sample_user_request():
    """Provide a sample user request for testing."""
    return "Research the benefits of renewable energy and create a summary"

@pytest.fixture(scope="session")
def check_openai_available():
    """Check if OpenAI API key is available."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set - skipping OpenAI tests")
    return True

@pytest.fixture(scope="session") 
def check_redis_available():
    """Check if Redis is available."""
    redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    if not redis_enabled:
        pytest.skip("REDIS_ENABLED not set to true - skipping Redis tests")
    
    try:
        import redis
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD")
        
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        
        # Test connection
        client.ping()
        return True
        
    except ImportError:
        pytest.skip("Redis Python package not installed")
    except redis.ConnectionError:
        pytest.skip("Redis connection failed - Redis not available")
    except Exception as e:
        pytest.skip(f"Redis setup check failed: {e}")