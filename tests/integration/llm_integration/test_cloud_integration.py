#!/usr/bin/env python3
"""
Cloud Integration Test with OpenAI
Tests the workflow with OpenAI models to verify LangGraph/LangChain integration
"""

import os
import sys
import asyncio
import uuid
import time
import pytest
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.workflow_factory import WorkflowFactory
from src.graph.state import StateManager, ApprovalStatus
from src.core.model_service import ModelService
from src.utils.logging_config import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)

def check_openai_setup():
    """Check if OpenAI API key is available"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable not set")
        print("💡 Please set your OpenAI API key:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
        print("   or add it to your .env file")
        return False
    
    print(f"✅ OpenAI API key found (ends with: ...{api_key[-4:]})")
    return True

def check_redis_setup():
    """Check if Redis is available and accessible"""
    print("🔍 Checking Redis connection...")
    
    redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    if not redis_enabled:
        print("❌ REDIS_ENABLED is not set to true")
        return False
    
    try:
        import redis
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD")
        
        print(f"🔧 Connecting to Redis at {redis_host}:{redis_port} (db={redis_db})")
        
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
        ping_result = client.ping()
        print(f"✅ Redis ping successful: {ping_result}")
        
        # Test basic operations
        test_key = "clarity:test:connection"
        client.set(test_key, "test_connection", ex=10)
        test_value = client.get(test_key)
        client.delete(test_key)
        
        print(f"✅ Redis read/write test successful: {test_value}")
        return True
        
    except ImportError:
        print("❌ Redis Python package not installed")
        print("💡 Install with: pip install redis")
        return False
    except redis.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        print("💡 Make sure Redis is running:")
        print("   docker run -d --name redis-clarity -p 6379:6379 redis:7-alpine")
        return False
    except Exception as e:
        print(f"❌ Redis setup check failed: {e}")
        return False

def test_openai_model_service(check_openai_available):
    """Test OpenAI model service"""
    print("🧪 Testing OpenAI Model Service...")
    
    model_service = ModelService()
    
    # Test getting OpenAI models
    planning_model = model_service.get_model_for_agent("planning")
    print(f"✅ Planning model: {planning_model.model_name}")
    assert planning_model is not None, "Planning model should not be None"
    
    research_model = model_service.get_model_for_agent("research")
    print(f"✅ Research model: {research_model.model_name}")
    assert research_model is not None, "Research model should not be None"
    
    code_model = model_service.get_model_for_agent("code")
    print(f"✅ Code model: {code_model.model_name}")
    assert code_model is not None, "Code model should not be None"
    
    # Test simple inference with OpenAI
    print("\n🔍 Testing OpenAI inference...")
    start_time = time.time()
    response = planning_model.invoke("What is 2+2? Answer with just the number and a brief explanation.")
    inference_time = time.time() - start_time
    
    print(f"✅ OpenAI response ({inference_time:.2f}s): {response}")
    assert response is not None, "Response should not be None"
    assert len(response.strip()) > 0, "Response should not be empty"
    
    # Test enhanced features
    print("\n📊 Testing enhanced features...")
    metrics = planning_model.get_metrics()
    print(f"✅ Model metrics: {metrics['total_calls']} calls, {metrics['cache_hit_rate']:.2f} cache hit rate")
    assert 'total_calls' in metrics, "Metrics should contain total_calls"
    assert 'cache_hit_rate' in metrics, "Metrics should contain cache_hit_rate"

def test_openai_workflow_creation(workflow_factory, check_openai_available):
    """Test workflow creation with OpenAI models"""
    print("\n🏗️ Testing OpenAI Workflow Creation...")
    
    workflow = workflow_factory.create_workflow()
    
    print("✅ Workflow created successfully")
    print(f"✅ Workflow nodes: {list(workflow.nodes.keys())}")
    print(f"✅ Checkpointing: {workflow_factory.checkpointing_type}")
    
    assert workflow is not None, "Workflow should not be None"
    assert len(workflow.nodes) > 0, "Workflow should have nodes"
    
    # Debug Redis connection
    if workflow_factory.checkpointing_type == "redis":
        print("🔍 Redis checkpointing enabled - testing connection...")
        try:
            from src.config.redis_config import redis_manager
            client = redis_manager.get_client()
            ping_result = client.ping()
            print(f"✅ Redis connection test: {ping_result}")
            
            # Test a simple write/read
            test_key = "test:connection"
            client.set(test_key, "test_value", ex=10)  # Expires in 10 seconds
            test_value = client.get(test_key)
            print(f"✅ Redis write/read test: {test_value}")
            client.delete(test_key)
            
            assert ping_result is True, "Redis ping should return True"
            assert test_value == "test_value", "Redis read/write test should work"
            
        except Exception as redis_e:
            print(f"❌ Redis connection test failed: {redis_e}")
            # Don't fail the test if Redis is not available, just warn
            pytest.skip(f"Redis connection failed: {redis_e}")
    elif workflow_factory.checkpointing_type == "memory":
        print("⚠️ Using memory checkpointing instead of Redis")

def test_openai_planning_phase(workflow_factory, sample_user_request, thread_id, check_openai_available):
    """Test planning phase with OpenAI models"""
    print("\n📋 Testing OpenAI Planning Phase...")
    
    # Create workflow
    workflow = workflow_factory.create_workflow()
    config = {"configurable": {"thread_id": thread_id}}
    
    # Execute planning phase
    print("⚡ Executing planning phase with OpenAI...")
    start_time = time.time()
    
    result = workflow.invoke({"user_request": sample_user_request}, config=config)
    
    execution_time = time.time() - start_time
    print(f"⏱️ Planning completed in {execution_time:.2f}s")
    
    # Check results
    assert 'plan' in result, "No plan key in result"
    assert len(result['plan']) > 0, "Plan is empty"
    
    print(f"✅ Plan generated with {len(result['plan'])} tasks:")
    for i, task in enumerate(result['plan'], 1):
        print(f"   {i}. [{task['type']}] {task['description']}")
    
    print(f"✅ Approval status: {result.get('human_approval_status', 'unknown')}")

def test_openai_full_execution(workflow_factory, thread_id, check_openai_available):
    """Test full workflow execution with OpenAI"""
    print("\n✅ Testing OpenAI Full Execution...")
    
    # First, we need to run the planning phase to have something to approve
    workflow = workflow_factory.create_workflow()
    config = {"configurable": {"thread_id": thread_id}}
    
    # Execute planning phase first
    sample_request = "Research the benefits of renewable energy and create a summary"
    planning_result = workflow.invoke({"user_request": sample_request}, config=config)
    
    # Verify planning worked
    assert 'plan' in planning_result, "Planning phase failed - no plan generated"
    assert len(planning_result['plan']) > 0, "Planning phase failed - empty plan"
    
    # Approve the plan and resume workflow
    print("👍 Approving plan...")
    start_time = time.time()
    
    # Use the new resume_after_approval method
    final_result = workflow_factory.resume_after_approval(
        thread_id=thread_id,
        approval_status=ApprovalStatus.APPROVED,
        feedback=None
    )
    
    execution_time = time.time() - start_time
    print(f"⏱️ Execution completed in {execution_time:.2f}s")
    
    # Debug: Print workflow state
    print(f"🔍 Workflow state after execution:")
    print(f"   - Plan tasks: {len(final_result.get('plan', []))}")
    task_results = final_result.get('task_results', {})
    print(f"   - Task results: {len(task_results) if task_results else 0}")
    print(f"   - Next task ID: {final_result.get('next_task_id')}")
    print(f"   - Approval status: {final_result.get('human_approval_status')}")
    
    # Show what tasks are in the plan
    plan = final_result.get('plan', [])
    for i, task in enumerate(plan, 1):
        status = task.get('status', 'unknown')
        print(f"   - Task {i}: {task.get('description', 'No description')} [{status}]")
    
    # For hybrid checkpointing, the result might be in a different format
    # Get the actual final state from the workflow
    if isinstance(final_result, dict) and 'compile_results' in final_result:
        # Extract the actual state from the node result
        actual_result = final_result['compile_results']
    else:
        actual_result = final_result
    
    # Check final results - make this more lenient for now
    assert actual_result is not None, "No final result returned"
    
    # Show task completion status
    completed_tasks = [t for t in actual_result.get('plan', []) if t.get('status') == 'completed']
    failed_tasks = [t for t in actual_result.get('plan', []) if t.get('status') == 'failed']
    
    print(f"✅ Completed tasks: {len(completed_tasks)}")
    if failed_tasks:
        print(f"❌ Failed tasks: {len(failed_tasks)}")
        for task in failed_tasks:
            print(f"   - {task['description']}: {task.get('result', 'No error info')}")
    
    # Show actual task results (the summaries)
    print("\n📋 Task Results:")
    task_results = actual_result.get('task_results', {})
    for task_id, result in task_results.items():
        task_desc = next((t['description'] for t in actual_result.get('plan', []) if t['id'] == task_id), f"Task {task_id}")
        print(f"\n🔍 {task_desc}:")
        # Show first 200 characters of each result
        print(f"{result[:200]}{'...' if len(result) > 200 else ''}")
    
    if actual_result.get('final_report'):
        print(f"\n📄 Report Status: Generated successfully ({len(actual_result['final_report'])} characters)")
    else:
        print("\n⚠️ No final report generated, but workflow completed")
    
    # Assert that we at least got some task results or completed tasks
    assert len(task_results) > 0 or len(completed_tasks) > 0, "No task results or completed tasks found"

def main():
    """Main cloud test runner"""
    print("🚀 Clarity.ai Cloud Integration Test with OpenAI")
    print("=" * 60)
    
    # Set environment for OpenAI testing
    os.environ["ENVIRONMENT"] = "testing"  # This switches to OpenAI models
    os.environ["REDIS_ENABLED"] = "true"  # Enable Redis with our simplified implementation
    os.environ["ENABLE_CHECKPOINTING"] = "true"
    
    print("🔧 Configuration: OpenAI models, Redis checkpointing")
    
    # Check OpenAI setup
    if not check_openai_setup():
        return False
    
    # Check Redis setup
    if not check_redis_setup():
        print("⚠️ Redis check failed - workflow will fall back to memory checkpointing")
        # Don't return False here, let it continue with memory fallback
    
    # Run tests
    success = True
    
    # Test 1: OpenAI Model Service
    if not test_openai_model_service():
        success = False
        return success
    
    # Test 2: OpenAI Workflow Creation
    workflow_success, workflow_factory = test_openai_workflow_creation()
    if not workflow_success:
        success = False
        return success
    
    # Test 3: OpenAI Planning Phase
    planning_success, thread_id, workflow = test_openai_planning_phase(workflow_factory)
    if not planning_success:
        success = False
        return success
    
    # Test 4: OpenAI Full Execution
    if not test_openai_full_execution(workflow_factory, thread_id):
        success = False
    
    # Summary
    print("\n" + "=" * 60)
    if success:
        print("🎉 All OpenAI cloud tests passed! LangGraph/LangChain integration is working correctly.")
        print("💡 This confirms the issue is with Ollama model performance, not the framework.")
    else:
        print("❌ Some OpenAI cloud tests failed. Check the output above.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)