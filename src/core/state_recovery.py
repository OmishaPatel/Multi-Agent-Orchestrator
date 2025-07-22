from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging
from src.core.redis_saver import RedisCheckpointSaver
from src.core.state import AgentState

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
    def __int__(self, checkpoint_saver: RedisCheckpointSaver):
        self.checkpoint_saver = checkpoint_saver

    def recover_latest_state(self, thread_id:str) -> Optional[AgentState]:
        try:
            config = {"configurable": {"thread_id": thread_id}}
            result = self.checkpoint_saver.get_tuple(config)

            if not result:
                logger.info("No checkpoint found for thread {thread_id}")
                return None

            checkpoint, metadata = result

            if 'agent_state' in checkpoint.channel_values:
                state = checkpoint.channel_values['agent_state']
                logger.info(f"Recovered state for thread {thread_id} from checkpoint {checkpoint.id}")
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
                    'checkpoint_id': checkpoint.id,
                    'timestamp': checkpoint.ts,
                    'step': metadata.step,
                    'source': metadata.source,
                    'created_at': datetime.fromtimestamp(checkpoint.ts, timezone.utc).isoformat()
                })
        except Exception as e:
            logger.error(f"Failed to list recovery points for thread {thread_id}: {e}")

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



