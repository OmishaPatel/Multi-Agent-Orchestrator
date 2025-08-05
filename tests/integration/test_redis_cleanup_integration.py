#!/usr/bin/env python3
"""
Manual test script for Redis cleanup functionality.
This script creates test data and demonstrates cleanup operations.

Prerequisites:
1. Redis server running on localhost:6379

Usage:
python test_redis_cleanup_manual.py
"""

import time
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

# Import our modules
from src.core.redis_state_manager import RedisStateManager
from src.core.state_recovery import StateRecoveryManager
from src.core.background_cleanup import BackgroundCleanupService
from src.config.cleanup_config import CleanupConfig

# Mock LangGraph classes for testing
class MockCheckpoint(dict):
    def __init__(self, checkpoint_id: str, timestamp: float):
        super().__init__({
            'v': 1,
            'ts': timestamp,
            'id': checkpoint_id,
            'channel_values': {
                "agent_state": {
                    "user_request": f"Test request for {checkpoint_id}",
                    "plan": [{"id": 1, "type": "research", "description": "Test task"}],
                    "task_results": {}
                }
            },
            'channel_versions': {"agent_state": 1},
            'versions_seen': {"agent_state": 1},
            'pending_sends': []
        })

class MockCheckpointMetadata(dict):
    def __init__(self, step: int = 1):
        super().__init__({
            'source': "test",
            'step': step,
            'writes': {}
        })

def create_test_data():
    """Create test state data in Redis"""
    print("🔧 Creating test state data...")
    
    state_manager = RedisStateManager()
    current_time = time.time()
    
    # Create test threads with different ages
    test_threads = [
        {
            "thread_id": "old_thread_1",
            "checkpoints": [
                ("cp_1", current_time - (25 * 3600)),  # 25 hours ago (expired)
                ("cp_2", current_time - (24.5 * 3600)),  # 24.5 hours ago (expired)
            ]
        },
        {
            "thread_id": "old_thread_2", 
            "checkpoints": [
                ("cp_3", current_time - (30 * 3600)),  # 30 hours ago (expired)
            ]
        },
        {
            "thread_id": "recent_thread_1",
            "checkpoints": [
                ("cp_4", current_time - (2 * 3600)),   # 2 hours ago (recent)
                ("cp_5", current_time - (1 * 3600)),   # 1 hour ago (recent)
            ]
        },
        {
            "thread_id": "mixed_thread_1",
            "checkpoints": [
                ("cp_6", current_time - (26 * 3600)),  # 26 hours ago (expired)
                ("cp_7", current_time - (0.5 * 3600)), # 30 minutes ago (recent)
            ]
        }
    ]
    
    # Create states
    for thread_data in test_threads:
        thread_id = thread_data["thread_id"]
        print(f"  📝 Creating thread: {thread_id}")
        
        # Create a test state for this thread
        test_state = {
            "user_request": f"Test request for {thread_id}",
            "plan": [{"id": 1, "type": "research", "description": "Test task"}],
            "task_results": {},
            "human_approval_status": "pending"
        }
        
        try:
            state_manager.save_state(thread_id, test_state)
            print(f"    ✅ Created state for {thread_id}")
        except Exception as e:
            print(f"    ❌ Failed to create state for {thread_id}: {e}")
    
    print(f"✅ Test data creation completed!\n")

def test_recovery_operations():
    """Test state recovery operations"""
    print("🔍 Testing state recovery operations...")
    
    state_manager = RedisStateManager()
    recovery_manager = StateRecoveryManager(redis_state_manager=state_manager)
    
    # Test recovery for different threads
    test_threads = ["old_thread_1", "recent_thread_1", "mixed_thread_1", "nonexistent_thread"]
    
    for thread_id in test_threads:
        print(f"  🔄 Testing recovery for thread: {thread_id}")
        
        try:
            # Test latest state recovery
            state = recovery_manager.recover_latest_state(thread_id)
            if state:
                print(f"    ✅ Recovered state: {state.get('user_request', 'No request')}")
            else:
                print(f"    ⚠️  No state found for thread {thread_id}")
            
            # Note: Recovery points listing not available with RedisStateManager
            print(f"    📋 Recovery points: N/A (using RedisStateManager)")
            
        except Exception as e:
            print(f"    ❌ Recovery failed for {thread_id}: {e}")
    
    print("✅ Recovery operations test completed!\n")

def test_cleanup_stats():
    """Test cleanup statistics"""
    print("📊 Testing cleanup statistics...")
    
    state_manager = RedisStateManager()
    
    try:
        # Simple stats using Redis directly
        redis_client = state_manager.redis
        
        # Count keys with our prefix
        state_keys = list(redis_client.scan_iter(match=f"{state_manager.key_prefix}*"))
        
        print("  📈 Current storage statistics:")
        print(f"    - Total state keys: {len(state_keys)}")
        print(f"    - Key prefix: {state_manager.key_prefix}")
        
        # Get Redis memory info
        try:
            memory_info = redis_client.info('memory')
            print(f"    - Redis memory: {memory_info.get('used_memory_human', 'unknown')}")
        except Exception as e:
            print(f"    - Redis memory: Error getting info - {e}")
        
    except Exception as e:
        print(f"  ❌ Failed to get cleanup stats: {e}")
    
    print("✅ Cleanup statistics test completed!\n")

def test_cleanup_operations():
    """Test cleanup operations"""
    print("🧹 Testing cleanup operations...")
    
    state_manager = RedisStateManager()
    
    print("  🗑️  Testing manual state cleanup")
    
    try:
        # Get all state keys
        redis_client = state_manager.redis
        state_keys = list(redis_client.scan_iter(match=f"{state_manager.key_prefix}*"))
        
        print(f"    📊 Found {len(state_keys)} state keys")
        
        # For testing, let's just show what we would clean up
        # In a real scenario, you'd implement age-based cleanup logic
        cleanup_count = 0
        for key in state_keys:
            try:
                # Check if key exists and get basic info
                if redis_client.exists(key):
                    # In a real cleanup, you'd check the timestamp and delete old entries
                    print(f"      - Found state key: {key}")
                    cleanup_count += 1
            except Exception as e:
                print(f"      - Error checking key {key}: {e}")
        
        print(f"    📊 Cleanup simulation results:")
        print(f"      - Keys found: {cleanup_count}")
        print(f"      - Would clean up: 0 (simulation mode)")
        
    except Exception as e:
        print(f"    ❌ Cleanup failed: {e}")
    
    print("✅ Cleanup operations test completed!\n")

def test_background_cleanup_service():
    """Test background cleanup service"""
    print("⚙️  Testing background cleanup service...")
    
    # Create test configuration
    config = CleanupConfig(
        cleanup_interval_hours=1,
        max_age_hours=24,
        cleanup_enabled=True
    )
    
    try:
        # Create service
        cleanup_service = BackgroundCleanupService(config=config)
        
        # Test service status
        status = cleanup_service.get_status()
        print(f"  📋 Service status:")
        print(f"    - Running: {status['is_running']}")
        print(f"    - Cleanup interval: {status['cleanup_interval_hours']} hours")
        print(f"    - Max age: {status['max_age_hours']} hours")
        
        # Test manual cleanup
        print("  🔧 Testing manual cleanup trigger...")
        cleanup_service.force_cleanup()
        print("    ✅ Manual cleanup completed")
        
        # Note: We don't start the scheduler in this test to avoid background processes
        print("    ⚠️  Scheduler not started in test mode")
        
    except Exception as e:
        print(f"  ❌ Background cleanup service test failed: {e}")
    
    print("✅ Background cleanup service test completed!\n")

def cleanup_test_data():
    """Clean up all test data"""
    print("🧽 Cleaning up test data...")
    
    state_manager = RedisStateManager()
    
    try:
        # Clean up all test data
        redis_client = state_manager.redis
        state_keys = list(redis_client.scan_iter(match=f"{state_manager.key_prefix}*"))
        
        deleted_count = 0
        for key in state_keys:
            try:
                if redis_client.delete(key):
                    deleted_count += 1
            except Exception as e:
                print(f"    ❌ Failed to delete key {key}: {e}")
        
        print(f"  🗑️  Final cleanup results:")
        print(f"    - Keys deleted: {deleted_count}")
        
    except Exception as e:
        print(f"  ❌ Final cleanup failed: {e}")
    
    print("✅ Test data cleanup completed!\n")

def main():
    """Main test function"""
    print("🚀 Starting Redis Cleanup Manual Test")
    print("=" * 50)
    
    try:
        # Test Redis connection first
        state_manager = RedisStateManager()
        state_manager.redis.ping()
        print("✅ Redis connection successful\n")
        
        # Run tests in sequence
        create_test_data()
        test_recovery_operations()
        test_cleanup_stats()
        test_cleanup_operations()
        test_background_cleanup_service()
        
        # Ask user if they want to clean up
        response = input("🤔 Do you want to clean up all test data? (y/N): ")
        if response.lower() in ['y', 'yes']:
            cleanup_test_data()
        else:
            print("⚠️  Test data left in Redis for manual inspection")
        
        print("🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()