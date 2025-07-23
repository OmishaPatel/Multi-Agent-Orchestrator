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
from src.config.redis_saver import RedisCheckpointSaver
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
    """Create test checkpoint data in Redis"""
    print("🔧 Creating test checkpoint data...")
    
    checkpoint_saver = RedisCheckpointSaver()
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
    
    # Create checkpoints
    for thread_data in test_threads:
        thread_id = thread_data["thread_id"]
        print(f"  📝 Creating thread: {thread_id}")
        
        for checkpoint_id, timestamp in thread_data["checkpoints"]:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint = MockCheckpoint(checkpoint_id, timestamp)
            metadata = MockCheckpointMetadata()
            
            try:
                checkpoint_saver.put(config, checkpoint, metadata)
                age_hours = (current_time - timestamp) / 3600
                print(f"    ✅ Created checkpoint {checkpoint_id} (age: {age_hours:.1f}h)")
            except Exception as e:
                print(f"    ❌ Failed to create checkpoint {checkpoint_id}: {e}")
    
    print(f"✅ Test data creation completed!\n")

def test_recovery_operations():
    """Test state recovery operations"""
    print("🔍 Testing state recovery operations...")
    
    checkpoint_saver = RedisCheckpointSaver()
    recovery_manager = StateRecoveryManager(checkpoint_saver)
    
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
            
            # Test recovery points listing
            recovery_points = recovery_manager.list_recovery_points(thread_id, limit=5)
            print(f"    📋 Recovery points: {len(recovery_points)}")
            
            for point in recovery_points:
                age_hours = (time.time() - point['timestamp']) / 3600
                print(f"      - {point['checkpoint_id']} (age: {age_hours:.1f}h)")
            
        except Exception as e:
            print(f"    ❌ Recovery failed for {thread_id}: {e}")
    
    print("✅ Recovery operations test completed!\n")

def test_cleanup_stats():
    """Test cleanup statistics"""
    print("📊 Testing cleanup statistics...")
    
    checkpoint_saver = RedisCheckpointSaver()
    recovery_manager = StateRecoveryManager(checkpoint_saver)
    
    try:
        stats = recovery_manager.get_cleanup_stats()
        
        print("  📈 Current storage statistics:")
        print(f"    - Total threads: {stats['total_threads']}")
        print(f"    - Total checkpoints: {stats['total_checkpoints']}")
        print(f"    - Oldest checkpoint age: {stats['oldest_checkpoint_age_hours']:.1f} hours")
        print(f"    - Newest checkpoint age: {stats['newest_checkpoint_age_hours']:.1f} hours")
        print(f"    - Cleanup candidates (24h): {stats['estimated_cleanup_candidates_24h']}")
        print(f"    - Cleanup candidates (7d): {stats['estimated_cleanup_candidates_7d']}")
        print(f"    - Redis memory: {stats['redis_memory_info'].get('used_memory_human', 'unknown')}")
        
    except Exception as e:
        print(f"  ❌ Failed to get cleanup stats: {e}")
    
    print("✅ Cleanup statistics test completed!\n")

def test_cleanup_operations():
    """Test cleanup operations"""
    print("🧹 Testing cleanup operations...")
    
    checkpoint_saver = RedisCheckpointSaver()
    recovery_manager = StateRecoveryManager(checkpoint_saver)
    
    # Test cleanup with different age thresholds
    age_thresholds = [48, 24, 12, 1]  # hours
    
    for max_age_hours in age_thresholds:
        print(f"  🗑️  Testing cleanup with max age: {max_age_hours} hours")
        
        try:
            stats = recovery_manager.cleanup_expired_states(max_age_hours=max_age_hours)
            
            print(f"    📊 Cleanup results:")
            print(f"      - Threads scanned: {stats['threads_scanned']}")
            print(f"      - Checkpoints deleted: {stats['checkpoints_deleted']}")
            print(f"      - Threads deleted: {stats['threads_deleted']}")
            print(f"      - Duration: {stats['cleanup_duration_seconds']:.2f}s")
            print(f"      - Errors: {len(stats['errors'])}")
            
            if stats['errors']:
                print(f"      - Error details: {stats['errors']}")
            
            # Don't run all cleanup tests to preserve some data
            if max_age_hours == 24:
                print("    ⏸️  Stopping cleanup tests to preserve data for other tests")
                break
                
        except Exception as e:
            print(f"    ❌ Cleanup failed for max_age_hours={max_age_hours}: {e}")
    
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
    
    checkpoint_saver = RedisCheckpointSaver()
    recovery_manager = StateRecoveryManager(checkpoint_saver)
    
    try:
        # Clean up all test data (very aggressive cleanup)
        stats = recovery_manager.cleanup_expired_states(max_age_hours=0)
        
        print(f"  🗑️  Final cleanup results:")
        print(f"    - Threads deleted: {stats['threads_deleted']}")
        print(f"    - Checkpoints deleted: {stats['checkpoints_deleted']}")
        
    except Exception as e:
        print(f"  ❌ Final cleanup failed: {e}")
    
    print("✅ Test data cleanup completed!\n")

def main():
    """Main test function"""
    print("🚀 Starting Redis Cleanup Manual Test")
    print("=" * 50)
    
    try:
        # Test Redis connection first
        checkpoint_saver = RedisCheckpointSaver()
        checkpoint_saver.redis.ping()
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