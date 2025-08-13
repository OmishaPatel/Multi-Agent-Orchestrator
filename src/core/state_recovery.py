from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging
import time
from src.core.redis_state_manager import RedisStateManager
from src.graph.state import AgentState

logger = logging.getLogger(__name__)

class StateRecoveryManager:
    """
    Manages state recovery and rollback operations for workflow resilience.
    
    This class provides high-level operations for:
    - Automatic recovery from the latest checkpoint
    - State validation and corruption detection
    - Cleanup of orphaned or expired states
    """
    def __init__(self, redis_state_manager: RedisStateManager = None):
        self.redis_state_manager = redis_state_manager or RedisStateManager()

    def recover_latest_state(self, thread_id: str) -> Optional[AgentState]:
        try:
            state = self.redis_state_manager.get_state(thread_id)
            if state:
                logger.info(f"Recovered state for thread {thread_id}")
                return state
            else:
                logger.info(f"No state found for thread {thread_id}")
                return None
        except Exception as e:
            logger.error(f"Failed to recover state for thread {thread_id}: {e}")
            return None
    
    def list_recovery_points(self, thread_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recovery points for a thread using LangGraph's memory checkpointing.
        
        This accesses historical checkpoints from LangGraph's memory store while
        the current state is maintained in Redis.
        """
        recovery_points = []

        try:
            # Import here to avoid circular imports
            from src.core.workflow_factory import WorkflowFactory
            
            # Create workflow with memory checkpointing to access historical checkpoints
            workflow_factory = WorkflowFactory()
            workflow = workflow_factory.create_workflow()
            config = {"configurable": {"thread_id": thread_id}}
            
            # Try to list checkpoints from LangGraph's memory checkpointer
            try:
                # Get available checkpoints from LangGraph
                for checkpoint, metadata in workflow.checkpointer.list(config, limit=limit):
                    recovery_points.append({
                        'checkpoint_id': checkpoint['id'],
                        'timestamp': checkpoint['ts'],
                        'step': metadata.get('step', 0),
                        'source': metadata.get('source', 'langgraph'),
                        'created_at': datetime.fromtimestamp(checkpoint['ts'], timezone.utc).isoformat()
                    })
                    
            except Exception as checkpoint_e:
                logger.warning(f"Could not access LangGraph checkpoints: {checkpoint_e}")
                
                # Fallback: provide current Redis state as a recovery point
                state = self.redis_state_manager.get_state(thread_id)
                if state:
                    recovery_points.append({
                        'checkpoint_id': f"redis_state_{thread_id}",
                        'timestamp': time.time(),
                        'step': 1,
                        'source': "redis_state_manager",
                        'created_at': datetime.now(timezone.utc).isoformat()
                    })
                    
        except Exception as e:
            logger.error(f"Failed to list recovery points for thread {thread_id}: {e}")
        
        return recovery_points

    def rollback_to_point(self, thread_id: str, checkpoint_id: str) -> bool:
        try:
            # Import here to avoid circular imports
            from src.core.workflow_factory import WorkflowFactory
            
            # Create workflow with memory checkpointing to access historical checkpoints
            workflow_factory = WorkflowFactory()
            workflow = workflow_factory.create_workflow()
            config = {"configurable": {"thread_id": thread_id}}
            
            # Try to get the specific checkpoint from LangGraph's memory checkpointer
            try:
                # Get the checkpoint from LangGraph's memory store
                checkpoint_tuple = workflow.checkpointer.get_tuple(config)
                if checkpoint_tuple and checkpoint_tuple[0]:
                    checkpoint, metadata = checkpoint_tuple
                    
                    # Check if this is the checkpoint we want to rollback to
                    if checkpoint.get('id') == checkpoint_id:
                        # Extract the agent state from the checkpoint
                        agent_state = checkpoint.get('channel_values', {}).get('agent_state')
                        if agent_state:
                            # Update Redis state with the rolled-back state
                            self.redis_state_manager.save_state(thread_id, agent_state)
                            logger.info(f"Successfully rolled back thread {thread_id} to checkpoint {checkpoint_id}")
                            return True
                    
                    # If not the exact checkpoint, we'd need to implement checkpoint traversal
                    # For now, log that we found a checkpoint but it's not the target
                    logger.warning(f"Found checkpoint {checkpoint.get('id')} but looking for {checkpoint_id}")
                
                logger.warning(f"Checkpoint {checkpoint_id} not found for thread {thread_id}")
                return False
                
            except Exception as checkpoint_e:
                logger.error(f"Failed to access checkpoint {checkpoint_id}: {checkpoint_e}")
                return False
                
        except Exception as e:
            logger.error(f"Error during rollback for thread {thread_id}: {e}")
            return False

    def validate_state_integrity(self, thread_id: str) -> Dict[str, Any]:
        validation_result = {
            'is_valid': True,
            'issues': [],
            'checkpoint_count': 0,
            'latest_checkpoint': None
        }

        try:
            # Count checkpoints
            recovery_points = self.list_recovery_points(thread_id)
            validation_result['checkpoint_count'] = len(recovery_points)

            if recovery_points:
                validation_result['latest_checkpoint'] = recovery_points[0]

                #try to recover latest state
                state = self.recover_latest_state(thread_id)
                if not state:
                    validation_result['is_valid'] = False
                    validation_result['issues'].append('Cannot recover latest state')
                else:
                    #validate state structure
                    required_fields = ['user_request', 'plan', 'task_results']
                    for field in required_fields:
                        if field not in state:
                            validation_result['is_valid'] = False
                            validation_result['issues'].append(f'Missing required field: {field}')
        except Exception as e:
            validation_result['is_valid'] = False
            validation_result['issues'].append(f'Validation error: {str(e)}')
            logger.error(f"State validation failed for thread {thread_id}: {e}")
        
        return validation_result


    def cleanup_expired_states(self, max_age_hours: int = 24) -> Dict[str, Any]:
        cleanup_stats = {
            "threads_scanned": 0,
            "checkpoints_deleted": 0,
            "threads_deleted": 0,
            "errors": [],
            "cleanup_duration_seconds": 0
        }

        start_time = time.time()
        cutoff_timestamp = time.time() - (max_age_hours * 3600)

        try:
            # Get all state keys using RedisStateManager's key pattern
            state_pattern = f"{self.redis_state_manager.key_prefix}*"
            redis_client = self.redis_state_manager.redis
            state_keys = list(redis_client.scan_iter(match=state_pattern))

            logger.info(f"Starting cleanup process - found {len(state_keys)} states to check (will delete those older than {max_age_hours} hours)")

            for state_key in state_keys:
                try:
                    cleanup_stats["threads_scanned"] += 1
                    
                    # Ensure state_key is a string (decode if bytes)
                    if isinstance(state_key, bytes):
                        state_key = state_key.decode('utf-8')
                    
                    # Extract thread_id from key (remove prefix)
                    thread_id = state_key.replace(self.redis_state_manager.key_prefix, "")
                    
                    # Get state data to check timestamp
                    state_data = redis_client.hgetall(state_key)
                    
                    if not state_data:
                        # Empty state, delete it
                        redis_client.delete(state_key)
                        cleanup_stats["threads_deleted"] += 1
                        logger.debug(f"Deleted empty state for thread {thread_id}")
                        continue
                    
                    # Check if state has updated_at timestamp
                    # Redis returns bytes, so we need to decode them
                    updated_at_bytes = state_data.get(b'updated_at') or state_data.get('updated_at')
                    if updated_at_bytes:
                        try:
                            # Decode bytes to string if necessary
                            if isinstance(updated_at_bytes, bytes):
                                updated_at_str = updated_at_bytes.decode('utf-8')
                            else:
                                updated_at_str = updated_at_bytes
                            
                            updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                            state_timestamp = updated_at.timestamp()
                            
                            if state_timestamp < cutoff_timestamp:
                                # State is expired, delete it
                                redis_client.delete(state_key)
                                cleanup_stats["threads_deleted"] += 1
                                cleanup_stats["checkpoints_deleted"] += 1  # Count as checkpoint for compatibility
                                logger.debug(f"Deleted expired state for thread {thread_id} (age: {(time.time() - state_timestamp) / 3600:.1f} hours)")
                        except (ValueError, AttributeError) as e:
                            logger.warning(f"Could not parse timestamp for thread {thread_id}: {e}")
                    else:
                        logger.debug(f"No timestamp found for thread {thread_id}, skipping")
                
                except Exception as e:
                    error_msg = f"Error cleaning state {state_key}: {str(e)}"
                    logger.error(error_msg)
                    cleanup_stats["errors"].append(error_msg)
            
            cleanup_stats["cleanup_duration_seconds"] = time.time() - start_time

            logger.info(
                f"Cleanup completed: {cleanup_stats['checkpoints_deleted']} states deleted, "
                f"{cleanup_stats['threads_deleted']} threads deleted, "
                f"{len(cleanup_stats['errors'])} errors in {cleanup_stats['cleanup_duration_seconds']:.2f}s"
            )

            return cleanup_stats

        except Exception as e:
            logger.error(f"Cleanup process failed: {e}")
            cleanup_stats["errors"].append(f"Cleanup process failed: {str(e)}")
            cleanup_stats["cleanup_duration_seconds"] = time.time() - start_time
            return cleanup_stats

    def _delete_entire_thread(self, thread_id: str) -> int:
        try:
            state_key = self.redis_state_manager._make_key(thread_id)
            deleted_count = self.redis_state_manager.redis.delete(state_key)
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            raise

    def _delete_old_states(self, cutoff_timestamp: float) -> int:
        try:
            deleted_count = 0
            state_pattern = f"{self.redis_state_manager.key_prefix}*"
            redis_client = self.redis_state_manager.redis
            
            for state_key in redis_client.scan_iter(match=state_pattern):
                try:
                    # Get state data to check timestamp
                    state_data = redis_client.hgetall(state_key)
                    # Redis returns bytes, so we need to decode them
                    updated_at_bytes = state_data.get(b'updated_at') or state_data.get('updated_at')
                    
                    if updated_at_bytes:
                        # Decode bytes to string if necessary
                        if isinstance(updated_at_bytes, bytes):
                            updated_at_str = updated_at_bytes.decode('utf-8')
                        else:
                            updated_at_str = updated_at_bytes
                        
                        updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                        if updated_at.timestamp() < cutoff_timestamp:
                            redis_client.delete(state_key)
                            deleted_count += 1
                except Exception as e:
                    logger.warning(f"Error checking state {state_key}: {e}")
                    continue
            
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete old states: {e}")
            raise


    def get_cleanup_stats(self) -> Dict[str, Any]:
        try:
            redis_client = self.redis_state_manager.redis
            state_pattern = f"{self.redis_state_manager.key_prefix}*"
            state_keys = list(redis_client.scan_iter(match=state_pattern))

            # Calculate age statistics
            oldest_state = None
            newest_state = None
            
            for state_key in state_keys:
                try:
                    # Ensure state_key is a string (decode if bytes)
                    if isinstance(state_key, bytes):
                        state_key = state_key.decode('utf-8')
                    
                    # Get state data to check timestamp
                    state_data = redis_client.hgetall(state_key)
                    # Redis returns bytes, so we need to decode them
                    updated_at_bytes = state_data.get(b'updated_at') or state_data.get('updated_at')
                    
                    if updated_at_bytes:
                        try:
                            # Decode bytes to string if necessary
                            if isinstance(updated_at_bytes, bytes):
                                updated_at_str = updated_at_bytes.decode('utf-8')
                            else:
                                updated_at_str = updated_at_bytes
                            
                            updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                            state_timestamp = updated_at.timestamp()
                            
                            if oldest_state is None or state_timestamp < oldest_state:
                                oldest_state = state_timestamp
                            
                            if newest_state is None or state_timestamp > newest_state:
                                newest_state = state_timestamp
                        except (ValueError, AttributeError):
                            continue
                
                except Exception as e:
                    logger.warning(f"Error processing state {state_key}: {e}")
            
            # Calculate age statistics
            now = time.time()
            oldest_age_hours = (now - oldest_state) / 3600 if oldest_state else 0
            newest_age_hours = (now - newest_state) / 3600 if newest_state else 0
            
            return {
                "total_threads": len(state_keys),
                "total_checkpoints": len(state_keys),  # For compatibility, treat states as checkpoints
                "oldest_checkpoint_age_hours": round(oldest_age_hours, 2),
                "newest_checkpoint_age_hours": round(newest_age_hours, 2),
                "oldest_checkpoint_timestamp": oldest_state,
                "newest_checkpoint_timestamp": newest_state,
                "estimated_cleanup_candidates_24h": self._count_cleanup_candidates(24),
                "estimated_cleanup_candidates_7d": self._count_cleanup_candidates(24 * 7),
                "redis_memory_info": self._get_redis_memory_info()
            }
            
        except Exception as e:
            logger.error(f"Failed to get cleanup stats: {e}")
            return {
                "error": str(e),
                "total_threads": 0,
                "total_checkpoints": 0
            }

    def _count_cleanup_candidates(self, max_age_hours: int) -> int:
        try:
            cutoff_timestamp = time.time() - (max_age_hours * 3600)
            redis_client = self.redis_state_manager.redis
            state_pattern = f"{self.redis_state_manager.key_prefix}*"
            state_keys = list(redis_client.scan_iter(match=state_pattern))
            
            cleanup_candidates = 0
            
            for state_key in state_keys:
                try:
                    # Check if state is old enough to be cleaned up
                    state_data = redis_client.hgetall(state_key)
                    # Redis returns bytes, so we need to decode them
                    updated_at_bytes = state_data.get(b'updated_at') or state_data.get('updated_at')
                    
                    if updated_at_bytes:
                        try:
                            # Decode bytes to string if necessary
                            if isinstance(updated_at_bytes, bytes):
                                updated_at_str = updated_at_bytes.decode('utf-8')
                            else:
                                updated_at_str = updated_at_bytes
                            
                            updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                            if updated_at.timestamp() < cutoff_timestamp:
                                cleanup_candidates += 1
                        except (ValueError, AttributeError):
                            continue
                except Exception:
                    continue
            
            return cleanup_candidates
            
        except Exception as e:
            logger.error(f"Failed to count cleanup candidates: {e}")
            return 0
    
    def _get_redis_memory_info(self) -> Dict[str, Any]:
        try:
            info = self.redis_state_manager.redis.info('memory')
            return {
                "used_memory_human": info.get('used_memory_human', 'unknown'),
                "used_memory_peak_human": info.get('used_memory_peak_human', 'unknown'),
                "used_memory_bytes": info.get('used_memory', 0),
                "used_memory_peak_bytes": info.get('used_memory_peak', 0)
            }
        except Exception as e:
            logger.warning(f"Could not get Redis memory info: {e}")
            return {"error": str(e)}
    








