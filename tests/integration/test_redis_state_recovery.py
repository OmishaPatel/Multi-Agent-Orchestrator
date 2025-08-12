#!/usr/bin/env python3
"""
Integration test for Redis state recovery functionality.
Tests the fixes we made to state_recovery.py and workflow_factory.py
"""

import pytest
import uuid
import time
from unittest.mock import Mock, patch
from src.core.redis_state_manager import RedisStateManager
from src.core.state_recovery import StateRecoveryManager
from src.core.workflow_factory import WorkflowFactory
from src.graph.state import StateManager, TaskStatus, ApprovalStatus

class TestRedisStateRecovery:
    """Test Redis state recovery functionality"""
    
    @pytest.fixture
    def redis_manager(self):
        """Create Redis state manager"""
        return RedisStateManager()
    
    @pytest.fixture
    def recovery_manager(self, redis_manager):
        """Create state recovery manager"""
        return StateRecoveryManager(redis_state_manager=redis_manager)
    
    @pytest.fixture
    def workflow_factory(self):
        """Create workflow factory"""
        return WorkflowFactory()
    
    @pytest.fixture
    def sample_state(self):
        """Create sample workflow state"""
        return {
            "user_request": "Test request for state recovery",
            "plan": [
                {
                    "id": 1,
                    "type": "research",
                    "description": "Research task",
                    "dependencies": [],
                    "status": TaskStatus.COMPLETED,
                    "result": "Research completed",
                    "started_at": "2025-08-12T10:00:00Z",
                    "completed_at": "2025-08-12T10:05:00Z"
                },
                {
                    "id": 2,
                    "type": "analysis",
                    "description": "Analysis task",
                    "dependencies": [1],
                    "status": TaskStatus.IN_PROGRESS,
                    "result": None,
                    "started_at": "2025-08-12T10:05:00Z",
                    "completed_at": None
                }
            ],
            "task_results": {
                1: "Research completed"
            },
            "next_task_id": 2,
            "messages": ["Planning completed", "Task 1 completed"],
            "human_approval_status": ApprovalStatus.APPROVED,
            "user_feedback": None,
            "final_report": None
        }
    
    def test_redis_connection(self, redis_manager):
        """Test Redis connection is working"""
        try:
            redis_manager.redis.ping()
            assert True, "Redis connection successful"
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    def test_state_save_and_recovery(self, redis_manager, sample_state):
        """Test saving and recovering state from Redis"""
        thread_id = f"test_recovery_{uuid.uuid4()}"
        
        try:
            # Save state
            redis_manager.save_state(thread_id, sample_state)
            
            # Recover state
            recovered_state = redis_manager.get_state(thread_id)
            
            # Verify recovery
            assert recovered_state is not None
            assert recovered_state["user_request"] == sample_state["user_request"]
            assert len(recovered_state["plan"]) == len(sample_state["plan"])
            assert recovered_state["human_approval_status"] == sample_state["human_approval_status"]
            assert recovered_state["next_task_id"] == sample_state["next_task_id"]
            
            # Verify task results
            assert recovered_state["task_results"] == sample_state["task_results"]
            
            # Verify plan structure
            for i, task in enumerate(recovered_state["plan"]):
                original_task = sample_state["plan"][i]
                assert task["id"] == original_task["id"]
                assert task["type"] == original_task["type"]
                assert task["status"] == original_task["status"]
                assert task["result"] == original_task["result"]
            
        finally:
            # Cleanup
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
    
    def test_state_recovery_with_missing_data(self, recovery_manager):
        """Test state recovery with missing or corrupted data"""
        thread_id = f"missing_data_{uuid.uuid4()}"
        
        # Try to recover non-existent state
        recovered_state = recovery_manager.recover_latest_state(thread_id)
        assert recovered_state is None
    
    def test_state_recovery_with_corrupted_data(self, redis_manager, recovery_manager):
        """Test state recovery with corrupted Redis data"""
        thread_id = f"corrupted_data_{uuid.uuid4()}"
        
        try:
            # Save corrupted data
            redis_manager.redis.set(f"{redis_manager.key_prefix}{thread_id}", "invalid_json_data")
            
            # Try to recover
            recovered_state = recovery_manager.recover_latest_state(thread_id)
            assert recovered_state is None  # Should handle corruption gracefully
            
        finally:
            # Cleanup
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
    
    def test_workflow_factory_state_recovery(self, workflow_factory, redis_manager, sample_state):
        """Test workflow factory state recovery functionality"""
        thread_id = f"workflow_recovery_{uuid.uuid4()}"
        
        try:
            # Save state directly to Redis
            redis_manager.save_state(thread_id, sample_state)
            
            # Test workflow factory recovery
            status = workflow_factory.get_workflow_status(thread_id)
            
            assert status is not None
            assert status.get("status") != "not_found"
            assert "user_request" in status
            assert "plan" in status
            assert len(status["plan"]) == 2
            
            # Verify task statuses are preserved
            completed_tasks = [t for t in status["plan"] if t["status"] == TaskStatus.COMPLETED]
            in_progress_tasks = [t for t in status["plan"] if t["status"] == TaskStatus.IN_PROGRESS]
            
            assert len(completed_tasks) == 1
            assert len(in_progress_tasks) == 1
            
        finally:
            # Cleanup
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
    
    def test_workflow_recovery_after_approval(self, workflow_factory, redis_manager):
        """Test workflow recovery after approval state"""
        thread_id = f"approval_recovery_{uuid.uuid4()}"
        
        # Create state in approval phase
        approval_state = {
            "user_request": "Test approval recovery",
            "plan": [
                {
                    "id": 1,
                    "type": "research",
                    "description": "Research task",
                    "dependencies": [],
                    "status": TaskStatus.PENDING,
                    "result": None,
                    "started_at": None,
                    "completed_at": None
                }
            ],
            "task_results": {},
            "next_task_id": 1,
            "messages": ["Planning completed"],
            "human_approval_status": ApprovalStatus.APPROVED,
            "user_feedback": None,
            "final_report": None
        }
        
        try:
            # Save approval state
            redis_manager.save_state(thread_id, approval_state)
            
            # Test recovery
            status = workflow_factory.get_workflow_status(thread_id)
            
            assert status is not None
            assert status["human_approval_status"] == ApprovalStatus.APPROVED
            assert status["next_task_id"] == 1
            assert len(status["plan"]) == 1
            
        finally:
            # Cleanup
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
    
    def test_state_validation_during_recovery(self, recovery_manager, redis_manager):
        """Test state validation during recovery process"""
        thread_id = f"validation_test_{uuid.uuid4()}"
        
        # Create invalid state (missing required fields)
        invalid_state = {
            "user_request": "Test request",
            # Missing plan, task_results, etc.
        }
        
        try:
            # Save invalid state
            redis_manager.save_state(thread_id, invalid_state)
            
            # Try to recover - should handle gracefully
            recovered_state = recovery_manager.recover_latest_state(thread_id)
            
            # Should either return None or a corrected state
            if recovered_state is not None:
                # If returned, should have basic structure
                assert "user_request" in recovered_state
                
        finally:
            # Cleanup
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
    
    def test_multiple_thread_recovery(self, redis_manager, recovery_manager):
        """Test recovery of multiple workflow threads"""
        thread_ids = [f"multi_test_{i}_{uuid.uuid4()}" for i in range(3)]
        
        try:
            # Create multiple states
            for i, thread_id in enumerate(thread_ids):
                state = {
                    "user_request": f"Test request {i}",
                    "plan": [
                        {
                            "id": 1,
                            "type": "research",
                            "description": f"Research task {i}",
                            "dependencies": [],
                            "status": TaskStatus.PENDING,
                            "result": None
                        }
                    ],
                    "task_results": {},
                    "next_task_id": 1,
                    "messages": [f"Planning completed for {i}"],
                    "human_approval_status": ApprovalStatus.PENDING,
                    "user_feedback": None,
                    "final_report": None
                }
                redis_manager.save_state(thread_id, state)
            
            # Test recovery of each
            for i, thread_id in enumerate(thread_ids):
                recovered_state = recovery_manager.recover_latest_state(thread_id)
                assert recovered_state is not None
                assert recovered_state["user_request"] == f"Test request {i}"
                assert len(recovered_state["plan"]) == 1
                
        finally:
            # Cleanup all
            for thread_id in thread_ids:
                redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
    
    def test_state_recovery_performance(self, redis_manager, recovery_manager):
        """Test state recovery performance with larger states"""
        thread_id = f"performance_test_{uuid.uuid4()}"
        
        # Create large state
        large_plan = []
        large_results = {}
        
        for i in range(50):  # 50 tasks
            task = {
                "id": i + 1,
                "type": "research" if i % 2 == 0 else "analysis",
                "description": f"Task {i + 1} description with some longer text to simulate real tasks",
                "dependencies": [i] if i > 0 else [],
                "status": TaskStatus.COMPLETED if i < 25 else TaskStatus.PENDING,
                "result": f"Result for task {i + 1}" if i < 25 else None,
                "started_at": "2025-08-12T10:00:00Z" if i < 25 else None,
                "completed_at": "2025-08-12T10:05:00Z" if i < 25 else None
            }
            large_plan.append(task)
            
            if i < 25:
                large_results[i + 1] = f"Result for task {i + 1}"
        
        large_state = {
            "user_request": "Large performance test request",
            "plan": large_plan,
            "task_results": large_results,
            "next_task_id": 26,
            "messages": [f"Message {i}" for i in range(10)],
            "human_approval_status": ApprovalStatus.APPROVED,
            "user_feedback": None,
            "final_report": None
        }
        
        try:
            # Measure save time
            start_time = time.time()
            redis_manager.save_state(thread_id, large_state)
            save_time = time.time() - start_time
            
            # Measure recovery time
            start_time = time.time()
            recovered_state = recovery_manager.recover_latest_state(thread_id)
            recovery_time = time.time() - start_time
            
            # Verify recovery
            assert recovered_state is not None
            assert len(recovered_state["plan"]) == 50
            assert len(recovered_state["task_results"]) == 25
            assert recovered_state["next_task_id"] == 26
            
            # Performance assertions (should be fast)
            assert save_time < 1.0, f"Save took too long: {save_time}s"
            assert recovery_time < 1.0, f"Recovery took too long: {recovery_time}s"
            
            print(f"Performance test - Save: {save_time:.3f}s, Recovery: {recovery_time:.3f}s")
            
        finally:
            # Cleanup
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")

def test_redis_state_recovery_integration():
    """Integration test for complete Redis state recovery flow"""
    print("🧪 Running Redis State Recovery Integration Test")
    
    # This can be run standalone
    redis_manager = RedisStateManager()
    recovery_manager = StateRecoveryManager(redis_state_manager=redis_manager)
    workflow_factory = WorkflowFactory()
    
    thread_id = f"integration_test_{uuid.uuid4()}"
    
    try:
        # Test Redis connection
        redis_manager.redis.ping()
        print("✅ Redis connection successful")
        
        # Create test state
        test_state = {
            "user_request": "Integration test request",
            "plan": [
                {
                    "id": 1,
                    "type": "research",
                    "description": "Research integration test",
                    "dependencies": [],
                    "status": TaskStatus.COMPLETED,
                    "result": "Research completed successfully",
                    "started_at": "2025-08-12T10:00:00Z",
                    "completed_at": "2025-08-12T10:05:00Z"
                }
            ],
            "task_results": {1: "Research completed successfully"},
            "next_task_id": None,
            "messages": ["Planning completed", "Task 1 completed"],
            "human_approval_status": ApprovalStatus.APPROVED,
            "user_feedback": None,
            "final_report": "Integration test completed successfully"
        }
        
        # Save state
        redis_manager.save_state(thread_id, test_state)
        print("✅ State saved to Redis")
        
        # Recover using recovery manager
        recovered_state = recovery_manager.recover_latest_state(thread_id)
        assert recovered_state is not None
        assert recovered_state["user_request"] == test_state["user_request"]
        print("✅ State recovered using StateRecoveryManager")
        
        # Recover using workflow factory
        workflow_status = workflow_factory.get_workflow_status(thread_id)
        assert workflow_status is not None
        assert workflow_status.get("status") != "not_found"
        print("✅ State recovered using WorkflowFactory")
        
        print("🎉 All Redis state recovery tests passed!")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        raise
    finally:
        # Cleanup
        try:
            redis_manager.redis.delete(f"{redis_manager.key_prefix}{thread_id}")
            print("✅ Test data cleaned up")
        except:
            pass

if __name__ == "__main__":
    # Run standalone integration test
    test_redis_state_recovery_integration()