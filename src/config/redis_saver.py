import json
import pickle
import base64
from typing import Any, Dict, List, Optional, Tuple, Iterator
from datetime import datetime, timezone
import logging
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.serde.base import SerializerProtocol
from src.config.redis_config import redis_manager
import redis

logger = logging.getLogger(__name__)

class RedisCheckpointSaver(BaseCheckpointSaver):
    """
    Redis-based checkpoint saver for LangGraph state persistence.
    
    This implementation provides:
    - Persistent state storage across service restarts
    - Thread-safe operations for concurrent workflows
    - Configurable serialization (JSON for simple types, pickle for complex)
    - Automatic cleanup of old checkpoints
    - State recovery and rollback capabilities
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        serde: Optional[SerializerProtocol] = None,
        key_prefix: str = "langgraph:checkpoint:",
        ttl_seconds: Optional[int] = None
    ):
        super().__init__(serde=serde)
        self.redis = redis_client or redis_manager.get_client()
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds  # Optional TTL for automatic cleanup
        
    def _make_key(self, thread_id: str, checkpoint_id: str) -> str:
        return f"{self.key_prefix}{thread_id}:{checkpoint_id}"
    
    def _make_thread_key(self, thread_id: str) -> str:
        return f"{self.key_prefix}thread:{thread_id}"
    
    def _serialize_checkpoint(self, checkpoint: Checkpoint) -> str:
        try:
            # Try JSON first for better readability and debugging
            checkpoint_dict = {
                'v': checkpoint.v,
                'ts': checkpoint.ts,
                'id': checkpoint.id,
                'channel_values': checkpoint.channel_values,
                'channel_versions': checkpoint.channel_versions,
                'versions_seen': checkpoint.versions_seen,
                'pending_sends': checkpoint.pending_sends
            }
            return json.dumps(checkpoint_dict, default=str)
        except (TypeError, ValueError):
            # Fallback to pickle for complex objects
            logger.debug("Using pickle serialization for complex checkpoint")
            return base64.b64encode(pickle.dumps(checkpoint)).decode('utf-8')
    
    def _deserialize_checkpoint(self, data: str) -> Checkpoint:
        try:
            # Try JSON first
            checkpoint_dict = json.loads(data)
            return Checkpoint(
                v=checkpoint_dict['v'],
                ts=checkpoint_dict['ts'],
                id=checkpoint_dict['id'],
                channel_values=checkpoint_dict['channel_values'],
                channel_versions=checkpoint_dict['channel_versions'],
                versions_seen=checkpoint_dict['versions_seen'],
                pending_sends=checkpoint_dict['pending_sends']
            )
        except (json.JSONDecodeError, KeyError):
            # Fallback to pickle
            logger.debug("Using pickle deserialization for checkpoint")
            return pickle.loads(base64.b64decode(data.encode('utf-8')))
    
    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata
    ) -> None:
        """Save checkpoint to Redis"""
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id is required in config")
        
        try:
            # Serialize checkpoint and metadata
            checkpoint_data = self._serialize_checkpoint(checkpoint)
            metadata_data = json.dumps({
                'source': metadata.source,
                'step': metadata.step,
                'writes': metadata.writes,
                'created_at': datetime.now(timezone.utc).isoformat()
            })
            
            # Store checkpoint
            checkpoint_key = self._make_key(thread_id, checkpoint.id)
            pipe = self.redis.pipeline()
            pipe.hset(checkpoint_key, mapping={
                'checkpoint': checkpoint_data,
                'metadata': metadata_data,
                'thread_id': thread_id,
                'checkpoint_id': checkpoint.id,
                'created_at': datetime.now(timezone.utc).isoformat()
            })
            
            # Set TTL if configured
            if self.ttl_seconds:
                pipe.expire(checkpoint_key, self.ttl_seconds)
            
            # Update thread index for listing checkpoints
            thread_key = self._make_thread_key(thread_id)
            pipe.zadd(thread_key, {checkpoint.id: checkpoint.ts})
            
            if self.ttl_seconds:
                pipe.expire(thread_key, self.ttl_seconds)
            
            pipe.execute()
            
            logger.debug(f"Saved checkpoint {checkpoint.id} for thread {thread_id}")
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint {checkpoint.id}: {e}")
            raise
    
    def get_tuple(self, config: Dict[str, Any]) -> Optional[Tuple[Checkpoint, CheckpointMetadata]]:
        thread_id = config.get("configurable", {}).get("thread_id")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        
        if not thread_id:
            return None
        
        try:
            if checkpoint_id:
                # Get specific checkpoint
                checkpoint_key = self._make_key(thread_id, checkpoint_id)
                data = self.redis.hgetall(checkpoint_key)
            else:
                # Get latest checkpoint
                thread_key = self._make_thread_key(thread_id)
                latest_checkpoints = self.redis.zrevrange(thread_key, 0, 0, withscores=True)
                
                if not latest_checkpoints:
                    return None
                
                latest_checkpoint_id = latest_checkpoints[0][0]
                checkpoint_key = self._make_key(thread_id, latest_checkpoint_id)
                data = self.redis.hgetall(checkpoint_key)
            
            if not data:
                return None
            
            # Deserialize checkpoint and metadata
            checkpoint = self._deserialize_checkpoint(data['checkpoint'])
            metadata = CheckpointMetadata(
                source=json.loads(data['metadata'])['source'],
                step=json.loads(data['metadata'])['step'],
                writes=json.loads(data['metadata'])['writes']
            )
            
            logger.debug(f"Retrieved checkpoint {checkpoint.id} for thread {thread_id}")
            return (checkpoint, metadata)
            
        except Exception as e:
            logger.error(f"Failed to get checkpoint for thread {thread_id}: {e}")
            return None
    
    def list(
        self,
        config: Dict[str, Any],
        limit: Optional[int] = 10,
        before: Optional[str] = None
    ) -> Iterator[Tuple[Checkpoint, CheckpointMetadata]]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return
        
        try:
            thread_key = self._make_thread_key(thread_id)
            
            # Get checkpoint IDs sorted by timestamp (newest first)
            if before:
                # Get checkpoints before a specific timestamp
                max_score = float(before)
                checkpoint_ids = self.redis.zrevrangebyscore(
                    thread_key, max_score, '-inf', start=0, num=limit
                )
            else:
                checkpoint_ids = self.redis.zrevrange(thread_key, 0, limit - 1)
            
            for checkpoint_id in checkpoint_ids:
                checkpoint_key = self._make_key(thread_id, checkpoint_id)
                data = self.redis.hgetall(checkpoint_key)
                
                if data:
                    checkpoint = self._deserialize_checkpoint(data['checkpoint'])
                    metadata = CheckpointMetadata(
                        source=json.loads(data['metadata'])['source'],
                        step=json.loads(data['metadata'])['step'],
                        writes=json.loads(data['metadata'])['writes']
                    )
                    yield (checkpoint, metadata)
                    
        except Exception as e:
            logger.error(f"Failed to list checkpoints for thread {thread_id}: {e}")
    
    def delete_thread(self, thread_id: str) -> None:
        try:
            thread_key = self._make_thread_key(thread_id)
            checkpoint_ids = self.redis.zrange(thread_key, 0, -1)
            
            # Delete all checkpoint keys
            keys_to_delete = [self._make_key(thread_id, cid) for cid in checkpoint_ids]
            keys_to_delete.append(thread_key)
            
            if keys_to_delete:
                self.redis.delete(*keys_to_delete)
                logger.info(f"Deleted {len(checkpoint_ids)} checkpoints for thread {thread_id}")
                
        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            raise
    
    def rollback_to_checkpoint(self, thread_id: str, checkpoint_id: str) -> bool:
        try:
            # Verify checkpoint exists
            checkpoint_key = self._make_key(thread_id, checkpoint_id)
            if not self.redis.exists(checkpoint_key):
                logger.error(f"Checkpoint {checkpoint_id} not found for thread {thread_id}")
                return False
            
            # Get checkpoint timestamp
            checkpoint_data = self.redis.hgetall(checkpoint_key)
            checkpoint = self._deserialize_checkpoint(checkpoint_data['checkpoint'])
            target_timestamp = checkpoint.ts
            
            # Remove all checkpoints newer than target
            thread_key = self._make_thread_key(thread_id)
            newer_checkpoints = self.redis.zrangebyscore(
                thread_key, target_timestamp + 1, '+inf'
            )
            
            if newer_checkpoints:
                # Delete newer checkpoint data
                keys_to_delete = [self._make_key(thread_id, cid) for cid in newer_checkpoints]
                self.redis.delete(*keys_to_delete)
                
                # Remove from thread index
                self.redis.zremrangebyscore(thread_key, target_timestamp + 1, '+inf')
                
                logger.info(f"Rolled back thread {thread_id} to checkpoint {checkpoint_id}, "
                           f"removed {len(newer_checkpoints)} newer checkpoints")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback thread {thread_id} to checkpoint {checkpoint_id}: {e}")
            return False
