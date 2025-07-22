from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging
import time
from src.config.redis_saver import RedisCheckpointSaver
from src.graph.state import AgentState

logger = logging.getLogger(__name__)

class StateRecoveryManager:
    """
    Manages state recovery and rollback operations for workflow resilience.
    
    This class provides high-level operations for:
    - Automatic recovery from the latest checkpoint
    - Manual rollback to specific points in time
    - State validation and corruption detection
    - Cleanup of orphaned or expired states
    """
    def __init__(self, checkpoint_saver: RedisCheckpointSaver):
        self.checkpoint_saver = checkpoint_saver

    def recover_latest_state(self, thread_id:str) -> Optional[AgentState]:
        try:
            config = {"configurable": {"thread_id": thread_id}}
            result = self.checkpoint_saver.get_tuple(config)

            if not result:
                logger.info(f"No checkpoint found for thread {thread_id}")
                return None

            checkpoint, metadata = result

            if 'agent_state' in checkpoint['channel_values']:
                state = checkpoint['channel_values']['agent_state']
                logger.info(f"Recovered state for thread {thread_id} from checkpoint {checkpoint['id']}")
                return state
            
            logger.warning(f"No agent_state found in checkpoint for thread {thread_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to recover state for thread {thread_id}: {e}")
            return None
    
    def list_recovery_points(self, thread_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        recovery_points = []

        try:
            config = {"configurable": {"thread_id": thread_id}}

            for checkpoint, metadata in self.checkpoint_saver.list(config, limit=limit):
                recovery_points.append({
                    'checkpoint_id': checkpoint['id'],
                    'timestamp': checkpoint['ts'],
                    'step': metadata['step'],
                    'source': metadata['source'],
                    'created_at': datetime.fromtimestamp(checkpoint['ts'], timezone.utc).isoformat()
                })
        except Exception as e:
            logger.error(f"Failed to list recovery points for thread {thread_id}: {e}")
        
        return recovery_points

    def rollback_to_point(self, thread_id: str, checkpoint_id: str) -> bool:
        try:
            success = self.checkpoint_saver.rollback_to_checkpoint(thread_id, checkpoint_id)

            if success:
                logger.info(f"Successfully rolled back thread {thread_id} to checkpoint {checkpoint_id}")
            else:
                logger.error(f"Failed to rollback thread {thread_id} to checkpoint {checkpoint_id}")
            return success
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
            thread_pattern = f"{self.checkpoint_saver.key_prefix}thread:*"
            # Use scan_iter for production-safe key iteration
            thread_keys = list(self.checkpoint_saver.redis.scan_iter(match=thread_pattern))

            logger.info(f"Starting cleanup of {len(thread_keys)} threads older than {max_age_hours} hours")

            for thread_key in thread_keys:
                try:
                    cleanup_stats["threads_scanned"] +=1
                    # Ensure thread_key is a string (decode if bytes)
                    if isinstance(thread_key, bytes):
                        thread_key = thread_key.decode('utf-8')
                    thread_id = thread_key.split(":")[-1] # Extract thread_id from key

                    # get all checkpoints for this thread
                    checkpoint_ids = self.checkpoint_saver.redis.zrange(thread_key, 0, -1)

                    if not checkpoint_ids:
                        self.checkpoint_saver.redis.delete(thread_key)
                        cleanup_stats["threads_deleted"] += 1
                        continue
                    # check if thread has any recent activity
                    latest_timestamp = self.checkpoint_saver.redis.zrevrange(
                        thread_key,0,0, withscores=True
                    )

                    if latest_timestamp and latest_timestamp[0][1] < cutoff_timestamp:
                        # entire thread is expired - delete everything
                        deleted_count = self._delete_entire_thread(thread_id, checkpoint_ids, thread_key)
                        cleanup_stats["checkpoints_deleted"] += deleted_count
                        cleanup_stats["threads_deleted"] += 1
                        logger.debug(f"Deleted expired thread {thread_id} with {deleted_count} checkpoints")

                    else:
                        # thread has recent activity - only delete old checkpoints
                        deleted_count = self._delete_old_checkpoints(thread_id, thread_key, cutoff_timestamp)
                        cleanup_stats["checkpoints_deleted"] += deleted_count
                        if deleted_count > 0:
                            logger.debug(f"Deleted {deleted_count} old checkpoints from active thread {thread_id}")
                
                except Exception as e:
                    error_msg = f"Error cleaning thread {thread_key}: {str(e)}"
                    logger.error(error_msg)
                    cleanup_stats["errors"].append(error_msg)
            cleanup_stats["cleanup_duration_seconds"] = time.time() - start_time

            logger.info(
                f"Cleanup completed: {cleanup_stats['checkpoints_deleted']} checkpoints deleted, "
                f"{cleanup_stats['threads_deleted']} threads deleted, "
                f"{len(cleanup_stats['errors'])} errors in {cleanup_stats['cleanup_duration_seconds']:.2f}s"
            )

            return cleanup_stats

        except Exception as e:
            logger.error(f"Cleanup process failed: {e}")
            cleanup_stats["errors"].append(f"Cleanup process failed: {str(e)}")
            cleanup_stats["cleanup_duration_seconds"] = time.time() - start_time
            return cleanup_stats

    def _delete_entire_thread(self, thread_id: str, checkpoint_ids: List[str], thread_key: str) -> int:
        try:
            keys_to_delete = [thread_key] # thread index

            for checkpoint_id in checkpoint_ids:
                checkpoint_key = self.checkpoint_saver._make_key(thread_id, checkpoint_id)
                keys_to_delete.append(checkpoint_key)

            batch_size = 100
            deleted_count = 0

            for i in range(0, len(keys_to_delete), batch_size):
                batch = keys_to_delete[i:i + batch_size]
                deleted_count += self.checkpoint_saver.redis.delete(*batch)

            return len(checkpoint_ids)

        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            raise

    def _delete_old_checkpoints(self, thread_id: str, thread_key: str, cutoff_timestamp: float) -> int:
        try:
            old_checkpoint_ids = self.checkpoint_saver.redis.zrangebyscore(
                thread_key, '-inf', cutoff_timestamp
            )

            if not old_checkpoint_ids:
                return 0

            # delete old checkpoint data

            keys_to_delete = []
            # delete old checkpoint data
            for checkpoint_id in old_checkpoint_ids:
                checkpoint_key = self.checkpoint_saver._make_key(thread_id, checkpoint_id)
                keys_to_delete.append(checkpoint_key)

            # delete checkpoint data
            if keys_to_delete:
                self.checkpoint_saver.redis.delete(*keys_to_delete)

            # remove from thread_index
            self.checkpoint_saver.redis.zremrangebyscore(thread_key, '-inf', cutoff_timestamp)

            return len(old_checkpoint_ids)
        
        except Exception as e:
            logger.error(f"Failed to delete old checkpoints for thread {thread_id}: {e}")
            raise


    def get_cleanup_stats(self) -> Dict[str, Any]:
        try:
            #count total threads
            thread_pattern = f"{self.checkpoint_saver.key_prefix}thread:*"
            thread_keys = list(self.checkpoint_saver.redis.scan_iter(match=thread_pattern))

            # count total checkpoints
            checkpoint_pattern = f"{self.checkpoint_saver.key_prefix}*"
            all_keys = list(self.checkpoint_saver.redis.scan_iter(match=checkpoint_pattern))

            # filter out thread index keys to get actual checkpoint keys
            checkpoint_keys = []
            for key in all_keys:
                # Ensure key is a string (decode if bytes)
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                if ":thread:" not in key:
                    checkpoint_keys.append(key)

            # calculate storage usage
            total_memory_usage = 0
            oldest_checkpoint = None
            newest_checkpoint = None
            for thread_key in thread_keys:
                try:
                    # Ensure thread_key is a string (decode if bytes)
                    if isinstance(thread_key, bytes):
                        thread_key = thread_key.decode('utf-8')
                    
                    # Get timestamp range for this thread
                    timestamps = self.checkpoint_saver.redis.zrange(thread_key, 0, -1, withscores=True)
                    
                    if timestamps:
                        thread_oldest = min(timestamps, key=lambda x: x[1])[1]
                        thread_newest = max(timestamps, key=lambda x: x[1])[1]
                        
                        if oldest_checkpoint is None or thread_oldest < oldest_checkpoint:
                            oldest_checkpoint = thread_oldest
                        
                        if newest_checkpoint is None or thread_newest > newest_checkpoint:
                            newest_checkpoint = thread_newest
                
                except Exception as e:
                    logger.warning(f"Error processing thread {thread_key}: {e}")
            
            # Calculate age statistics
            now = time.time()
            oldest_age_hours = (now - oldest_checkpoint) / 3600 if oldest_checkpoint else 0
            newest_age_hours = (now - newest_checkpoint) / 3600 if newest_checkpoint else 0
            
            return {
                "total_threads": len(thread_keys),
                "total_checkpoints": len(checkpoint_keys),
                "oldest_checkpoint_age_hours": round(oldest_age_hours, 2),
                "newest_checkpoint_age_hours": round(newest_age_hours, 2),
                "oldest_checkpoint_timestamp": oldest_checkpoint,
                "newest_checkpoint_timestamp": newest_checkpoint,
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
            thread_pattern = f"{self.checkpoint_saver.key_prefix}thread:*"
            thread_keys = list(self.checkpoint_saver.redis.scan_iter(match=thread_pattern))
            
            cleanup_candidates = 0
            
            for thread_key in thread_keys:
                try:
                    # Count old checkpoints in this thread
                    old_checkpoints = self.checkpoint_saver.redis.zrangebyscore(
                        thread_key, '-inf', cutoff_timestamp
                    )
                    cleanup_candidates += len(old_checkpoints)
                except Exception:
                    continue
            
            return cleanup_candidates
            
        except Exception as e:
            logger.error(f"Failed to count cleanup candidates: {e}")
            return 0
    
    def _get_redis_memory_info(self) -> Dict[str, Any]:
        try:
            info = self.checkpoint_saver.redis.info('memory')
            return {
                "used_memory_human": info.get('used_memory_human', 'unknown'),
                "used_memory_peak_human": info.get('used_memory_peak_human', 'unknown'),
                "used_memory_bytes": info.get('used_memory', 0),
                "used_memory_peak_bytes": info.get('used_memory_peak', 0)
            }
        except Exception as e:
            logger.warning(f"Could not get Redis memory info: {e}")
            return {"error": str(e)}
    








