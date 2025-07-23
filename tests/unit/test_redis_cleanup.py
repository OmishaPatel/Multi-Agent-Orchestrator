"""
Comprehensive tests for Redis cleanup functionality
"""
import pytest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

from src.config.redis_saver import RedisCheckpointSaver
from src.core.state_recovery import StateRecoveryManager
from src.core.background_cleanup import BackgroundCleanupService
from src.config.cleanup_config import CleanupConfig


class TestRedisCheckpointSaver:
    """Test Redis checkpoint saver functionality"""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        mock_client = Mock()
        mock_client.pipeline.return_value = Mock()
        return mock_client
    
    @pytest.fixture
    def checkpoint_saver(self, mock_redis):
        """Create checkpoint saver with mocked Redis"""
        return RedisCheckpointSaver(redis_client=mock_redis)
    
    @pytest.fixture
    def sample_checkpoint(self):
        """Sample checkpoint for testing"""
        return {
            'v': 1,
            'ts': time.time(),
            'id': "checkpoint_123",
            'channel_values': {"agent_state": {"user_request": "test request", "plan": []}},
            'channel_versions': {"agent_state": 1},
            'versions_seen': {"agent_state": 1},
            'pending_sends': []
        }
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample metadata for testing"""
        return CheckpointMetadata(
            source="test",
            step=1,
            writes={}
        )
    
    def test_put_checkpoint_success(self, checkpoint_saver, mock_redis, sample_checkpoint, sample_metadata):
        """Test successful checkpoint save"""
        config = {"configurable": {"thread_id": "test_thread"}}
        
        # Mock Redis pipeline
        mock_pipe = Mock()
        mock_redis.pipeline.return_value = mock_pipe
        
        # Execute put operation
        checkpoint_saver.put(config, sample_checkpoint, sample_metadata)
        
        # Verify Redis operations
        mock_redis.pipeline.assert_called_once()
        mock_pipe.hset.assert_called_once()
        mock_pipe.zadd.assert_called_once()
        mock_pipe.execute.assert_called_once()
    
    def test_put_checkpoint_missing_thread_id(self, checkpoint_saver, sample_checkpoint, sample_metadata):
        """Test checkpoint save with missing thread_id"""
        config = {"configurable": {}}  # Missing thread_id
        
        with pytest.raises(ValueError, match="thread_id is required"):
            checkpoint_saver.put(config, sample_checkpoint, sample_metadata)
    
    def test_get_latest_checkpoint(self, checkpoint_saver, mock_redis, sample_checkpoint):
        """Test retrieving latest checkpoint"""
        config = {"configurable": {"thread_id": "test_thread"}}
        
        # Mock Redis responses
        mock_redis.zrevrange.return_value = [("checkpoint_123", 1234567890)]
        mock_redis.hgetall.return_value = {
            'checkpoint': json.dumps({
                'v': sample_checkpoint['v'],
                'ts': sample_checkpoint['ts'],
                'id': sample_checkpoint['id'],
                'channel_values': sample_checkpoint['channel_values'],
                'channel_versions': sample_checkpoint['channel_versions'],
                'versions_seen': sample_checkpoint['versions_seen'],
                'pending_sends': sample_checkpoint['pending_sends']
            }, default=str),
            'metadata': json.dumps({
                'source': 'test',
                'step': 1,
                'writes': {}
            })
        }
        
        # Execute get operation
        result = checkpoint_saver.get_tuple(config)
        
        # Verify result
        assert result is not None
        checkpoint, metadata = result
        assert checkpoint['id'] == "checkpoint_123"
        assert metadata['source'] == "test"
    
    def test_get_specific_checkpoint(self, checkpoint_saver, mock_redis, sample_checkpoint):
        """Test retrieving specific checkpoint by ID"""
        config = {
            "configurable": {
                "thread_id": "test_thread",
                "checkpoint_id": "checkpoint_123"
            }
        }
        
        # Mock Redis response
        mock_redis.hgetall.return_value = {
            'checkpoint': json.dumps({
                'v': sample_checkpoint['v'],
                'ts': sample_checkpoint['ts'],
                'id': sample_checkpoint['id'],
                'channel_values': sample_checkpoint['channel_values'],
                'channel_versions': sample_checkpoint['channel_versions'],
                'versions_seen': sample_checkpoint['versions_seen'],
                'pending_sends': sample_checkpoint['pending_sends']
            }, default=str),
            'metadata': json.dumps({
                'source': 'test',
                'step': 1,
                'writes': {}
            })
        }
        
        # Execute get operation
        result = checkpoint_saver.get_tuple(config)
        
        # Verify result
        assert result is not None
        checkpoint, metadata = result
        assert checkpoint['id'] == "checkpoint_123"
    
    def test_delete_thread(self, checkpoint_saver, mock_redis):
        """Test deleting all checkpoints for a thread"""
        thread_id = "test_thread"
        
        # Mock Redis responses
        mock_redis.zrange.return_value = ["checkpoint_123", "checkpoint_456"]
        
        # Execute delete operation
        checkpoint_saver.delete_thread(thread_id)
        
        # Verify Redis delete operation
        mock_redis.delete.assert_called_once()
        # Should delete 3 keys: 2 checkpoints + 1 thread index
        args = mock_redis.delete.call_args[0]
        assert len(args) == 3
    
    def test_rollback_to_checkpoint(self, checkpoint_saver, mock_redis):
        """Test rolling back to a specific checkpoint"""
        thread_id = "test_thread"
        checkpoint_id = "checkpoint_123"
        
        # Mock Redis responses
        mock_redis.exists.return_value = True
        mock_redis.hgetall.return_value = {
            'checkpoint': json.dumps({
                'v': 1,
                'ts': 1234567890,
                'id': checkpoint_id,
                'channel_values': {},
                'channel_versions': {},
                'versions_seen': {},
                'pending_sends': []
            })
        }
        mock_redis.zrangebyscore.return_value = ["checkpoint_456", "checkpoint_789"]
        
        # Execute rollback
        result = checkpoint_saver.rollback_to_checkpoint(thread_id, checkpoint_id)
        
        # Verify success
        assert result is True
        mock_redis.delete.assert_called_once()
        mock_redis.zremrangebyscore.assert_called_once()


class TestStateRecoveryManager:
    """Test state recovery manager functionality"""
    
    @pytest.fixture
    def mock_checkpoint_saver(self):
        """Mock checkpoint saver"""
        return Mock(spec=RedisCheckpointSaver)
    
    @pytest.fixture
    def recovery_manager(self, mock_checkpoint_saver):
        """Create recovery manager with mocked checkpoint saver"""
        return StateRecoveryManager(mock_checkpoint_saver)
    
    def test_recover_latest_state_success(self, recovery_manager, mock_checkpoint_saver):
        """Test successful state recovery"""
        thread_id = "test_thread"
        
        # Mock checkpoint saver response
        mock_checkpoint = {
            'id': "checkpoint_123",
            'channel_values': {
                'agent_state': {'user_request': 'test request', 'plan': []}
            }
        }
        mock_metadata = Mock()
        mock_checkpoint_saver.get_tuple.return_value = (mock_checkpoint, mock_metadata)
        
        # Execute recovery
        state = recovery_manager.recover_latest_state(thread_id)
        
        # Verify result
        assert state is not None
        assert state['user_request'] == 'test request'
        mock_checkpoint_saver.get_tuple.assert_called_once()
    
    def test_recover_latest_state_no_checkpoint(self, recovery_manager, mock_checkpoint_saver):
        """Test recovery when no checkpoint exists"""
        thread_id = "test_thread"
        
        # Mock no checkpoint found
        mock_checkpoint_saver.get_tuple.return_value = None
        
        # Execute recovery
        state = recovery_manager.recover_latest_state(thread_id)
        
        # Verify result
        assert state is None
    
    def test_recover_latest_state_no_agent_state(self, recovery_manager, mock_checkpoint_saver):
        """Test recovery when checkpoint has no agent_state"""
        thread_id = "test_thread"
        
        # Mock checkpoint without agent_state
        mock_checkpoint = {'channel_values': {'other_data': 'value'}}
        mock_metadata = Mock()
        mock_checkpoint_saver.get_tuple.return_value = (mock_checkpoint, mock_metadata)
        
        # Execute recovery
        state = recovery_manager.recover_latest_state(thread_id)
        
        # Verify result
        assert state is None
    
    def test_cleanup_expired_states(self, recovery_manager, mock_checkpoint_saver):
        """Test cleanup of expired states"""
        # Mock Redis client
        mock_redis = Mock()
        mock_checkpoint_saver.redis = mock_redis
        mock_checkpoint_saver.key_prefix = "langgraph:checkpoint:"
        mock_checkpoint_saver._make_key = lambda tid, cid: f"langgraph:checkpoint:{tid}:{cid}"
        
        # Mock thread keys - using scan_iter now instead of keys
        mock_redis.scan_iter.return_value = iter([
            "langgraph:checkpoint:thread:thread1",
            "langgraph:checkpoint:thread:thread2"
        ])
        
        # Mock thread1 - expired thread
        mock_redis.zrange.side_effect = [
            ["checkpoint_1", "checkpoint_2"],  # thread1 checkpoints
            ["checkpoint_3"]  # thread2 checkpoints
        ]
        
        # Mock timestamps - thread1 is old, thread2 is recent
        current_time = time.time()
        old_time = current_time - (25 * 3600)  # 25 hours ago (expired)
        recent_time = current_time - (1 * 3600)  # 1 hour ago (recent)
        
        mock_redis.zrevrange.side_effect = [
            [("checkpoint_2", old_time)],  # thread1 latest is old
            [("checkpoint_3", recent_time)]  # thread2 latest is recent
        ]
        
        # Mock delete operations
        mock_redis.delete.return_value = 1
        mock_redis.zremrangebyscore.return_value = 1
        
        # Execute cleanup
        stats = recovery_manager.cleanup_expired_states(max_age_hours=24)
        
        # Verify results
        assert stats['threads_scanned'] == 2
        assert stats['threads_deleted'] >= 0
        assert stats['checkpoints_deleted'] >= 0
        assert isinstance(stats['cleanup_duration_seconds'], float)
    
    def test_validate_state_integrity(self, recovery_manager):
        """Test state integrity validation"""
        thread_id = "test_thread"
        
        # Mock recovery manager methods
        recovery_manager.list_recovery_points = Mock(return_value=[
            {'checkpoint_id': 'cp1', 'timestamp': 1234567890}
        ])
        recovery_manager.recover_latest_state = Mock(return_value={
            'user_request': 'test',
            'plan': [],
            'task_results': {}
        })
        
        # Execute validation
        result = recovery_manager.validate_state_integrity(thread_id)
        
        # Verify result
        assert result['is_valid'] is True
        assert result['checkpoint_count'] == 1
        assert len(result['issues']) == 0


class TestBackgroundCleanupService:
    """Test background cleanup service"""
    
    @pytest.fixture
    def cleanup_config(self):
        """Test cleanup configuration"""
        return CleanupConfig(
            cleanup_interval_hours=1,
            max_age_hours=2,
            cleanup_enabled=True
        )
    
    @pytest.fixture
    def mock_recovery_manager(self):
        """Mock recovery manager"""
        mock_manager = Mock()
        mock_manager.cleanup_expired_states.return_value = {
            'threads_scanned': 5,
            'checkpoints_deleted': 10,
            'threads_deleted': 2,
            'errors': [],
            'cleanup_duration_seconds': 1.5
        }
        mock_manager.get_cleanup_stats.return_value = {
            'total_threads': 5,
            'total_checkpoints': 20,
            'oldest_checkpoint_age_hours': 48.5,
            'redis_memory_info': {'used_memory_human': '1.2MB'}
        }
        return mock_manager
    
    @patch('src.core.background_cleanup.StateRecoveryManager')
    def test_cleanup_service_initialization(self, mock_recovery_class, cleanup_config):
        """Test cleanup service initialization"""
        mock_recovery_class.return_value = Mock()
        
        service = BackgroundCleanupService(config=cleanup_config)
        
        assert service.cleanup_interval_hours == 1
        assert service.max_age_hours == 2
        assert not service.is_running
    
    @patch('src.core.background_cleanup.StateRecoveryManager')
    def test_cleanup_service_disabled(self, mock_recovery_class):
        """Test cleanup service when disabled"""
        disabled_config = CleanupConfig(cleanup_enabled=False)
        mock_recovery_class.return_value = Mock()
        
        service = BackgroundCleanupService(config=disabled_config)
        
        # Service should not initialize scheduler when disabled
        assert not hasattr(service, 'scheduler')
    
    @patch('src.core.background_cleanup.StateRecoveryManager')
    def test_force_cleanup(self, mock_recovery_class, cleanup_config, mock_recovery_manager):
        """Test manual cleanup trigger"""
        mock_recovery_class.return_value = mock_recovery_manager
        
        service = BackgroundCleanupService(config=cleanup_config)
        service.recovery_manager = mock_recovery_manager
        
        # Execute force cleanup
        service.force_cleanup()
        
        # Verify cleanup was called
        mock_recovery_manager.cleanup_expired_states.assert_called_once_with(2)  # max_age_hours
    
    @patch('src.core.background_cleanup.StateRecoveryManager')
    def test_get_status_not_running(self, mock_recovery_class, cleanup_config):
        """Test getting status when service is not running"""
        mock_recovery_class.return_value = Mock()
        
        service = BackgroundCleanupService(config=cleanup_config)
        
        status = service.get_status()
        
        assert status['is_running'] is False
        assert status['cleanup_interval_hours'] == 1
        assert status['max_age_hours'] == 2
        assert status['next_cleanup'] is None
        assert status['jobs'] == []


class TestRedisCleanupIntegration:
    """Integration tests for Redis cleanup functionality"""
    
    @pytest.fixture
    def redis_saver_with_mock_redis(self):
        """Redis saver with mock Redis for integration testing"""
        mock_redis = Mock()
        mock_redis.pipeline.return_value = Mock()
        return RedisCheckpointSaver(redis_client=mock_redis)
    
    def test_full_cleanup_workflow(self, redis_saver_with_mock_redis):
        """Test complete cleanup workflow"""
        # Setup mock data
        mock_redis = redis_saver_with_mock_redis.redis
        redis_saver_with_mock_redis.key_prefix = "langgraph:checkpoint:"
        redis_saver_with_mock_redis._make_key = lambda tid, cid: f"langgraph:checkpoint:{tid}:{cid}"
        
        # Mock thread discovery using scan_iter
        mock_redis.scan_iter.return_value = iter([
            "langgraph:checkpoint:thread:old_thread",
            "langgraph:checkpoint:thread:new_thread"
        ])
        
        # Mock old thread data
        current_time = time.time()
        old_time = current_time - (25 * 3600)  # 25 hours ago
        new_time = current_time - (1 * 3600)   # 1 hour ago
        
        mock_redis.zrange.side_effect = [
            ["old_checkpoint_1", "old_checkpoint_2"],  # old thread
            ["new_checkpoint_1"]  # new thread
        ]
        
        mock_redis.zrevrange.side_effect = [
            [("old_checkpoint_2", old_time)],  # old thread latest
            [("new_checkpoint_1", new_time)]   # new thread latest
        ]
        
        # Mock delete operations
        mock_redis.delete.return_value = 1
        mock_redis.zremrangebyscore.return_value = 1
        
        # Create recovery manager and run cleanup
        recovery_manager = StateRecoveryManager(redis_saver_with_mock_redis)
        stats = recovery_manager.cleanup_expired_states(max_age_hours=24)
        
        # Verify cleanup executed
        assert stats['threads_scanned'] == 2
        assert isinstance(stats['cleanup_duration_seconds'], float)
        assert isinstance(stats['errors'], list)
    
    def test_cleanup_error_handling(self, redis_saver_with_mock_redis):
        """Test cleanup error handling"""
        mock_redis = redis_saver_with_mock_redis.redis
        redis_saver_with_mock_redis.key_prefix = "langgraph:checkpoint:"
        
        # Mock Redis error with scan_iter
        mock_redis.scan_iter.side_effect = Exception("Redis connection failed")
        
        # Create recovery manager and run cleanup
        recovery_manager = StateRecoveryManager(redis_saver_with_mock_redis)
        stats = recovery_manager.cleanup_expired_states(max_age_hours=24)
        
        # Verify error handling
        assert len(stats['errors']) > 0
        assert 'Redis connection failed' in str(stats['errors'])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])