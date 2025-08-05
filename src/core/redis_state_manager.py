import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from src.config.redis_config import redis_manager
from src.graph.state import AgentState

logger = logging.getLogger(__name__)

class RedisStateManager:
    """
    Redis-based state manager that works alongside LangGraph's memory checkpointing.
    
    This provides persistent state storage while letting LangGraph handle the workflow execution
    with its native memory checkpointing system.
    """
    
    def __init__(self, key_prefix: str = "clarity:state:", ttl_seconds: int = 3600):
        self.redis = redis_manager.get_client()
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds
    
    def _make_key(self, thread_id: str) -> str:
        return f"{self.key_prefix}{thread_id}"
    
    def _serialize_state(self, state: Dict[str, Any]) -> str:
        try:
            # Create a serializable copy of the state
            serializable_state = {}
            
            for key, value in state.items():
                if key == 'plan' and isinstance(value, list):
                    # Handle SubTask list serialization
                    serializable_state[key] = [dict(task) for task in value]
                elif key == 'task_results' and isinstance(value, dict):
                    # Ensure all keys are strings for JSON compatibility
                    serializable_state[key] = {str(k): v for k, v in value.items()}
                elif key == 'messages' and isinstance(value, list):
                    # Handle messages list
                    serializable_state[key] = list(value)
                else:
                    serializable_state[key] = value
            
            return json.dumps(serializable_state, default=str)
        except Exception as e:
            logger.error(f"Failed to serialize state: {e}")
            raise
    
    def _deserialize_state(self, data: str) -> Dict[str, Any]:
        try:
            state = json.loads(data)
            
            # Convert task_results keys back to integers
            if 'task_results' in state and isinstance(state['task_results'], dict):
                state['task_results'] = {int(k): v for k, v in state['task_results'].items()}
            
            return state
        except Exception as e:
            logger.error(f"Failed to deserialize state: {e}")
            raise
    
    def save_state(self, thread_id: str, state: Dict[str, Any]) -> None:
        try:
            key = self._make_key(thread_id)
            serialized_state = self._serialize_state(state)
            
            # Store with metadata
            data = {
                'state': serialized_state,
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'thread_id': thread_id
            }
            
            pipe = self.redis.pipeline()
            pipe.hset(key, mapping=data)
            if self.ttl_seconds:
                pipe.expire(key, self.ttl_seconds)
            pipe.execute()
            
            logger.debug(f"Saved state for thread {thread_id}")
            
        except Exception as e:
            logger.error(f"Failed to save state for thread {thread_id}: {e}")
            raise
    
    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        try:
            key = self._make_key(thread_id)
            data = self.redis.hgetall(key)
            
            if not data or 'state' not in data:
                return None
            
            state = self._deserialize_state(data['state'])
            logger.debug(f"Retrieved state for thread {thread_id}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to get state for thread {thread_id}: {e}")
            return None
    
    def delete_state(self, thread_id: str) -> None:
        try:
            key = self._make_key(thread_id)
            self.redis.delete(key)
            logger.debug(f"Deleted state for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to delete state for thread {thread_id}: {e}")
            raise
    
    def update_state(self, thread_id: str, updates: Dict[str, Any]) -> None:
        try:
            current_state = self.get_state(thread_id)
            if current_state:
                current_state.update(updates)
                self.save_state(thread_id, current_state)
            else:
                logger.warning(f"No existing state found for thread {thread_id}, creating new state")
                self.save_state(thread_id, updates)
        except Exception as e:
            logger.error(f"Failed to update state for thread {thread_id}: {e}")
            raise
    
    def list_threads(self, limit: int = 100) -> list:
        try:
            pattern = f"{self.key_prefix}*"
            keys = list(self.redis.scan_iter(match=pattern, count=limit))
            thread_ids = [key.decode('utf-8').replace(self.key_prefix, '') for key in keys]
            return thread_ids
        except Exception as e:
            logger.error(f"Failed to list threads: {e}")
            return []