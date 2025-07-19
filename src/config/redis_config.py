import os
import redis
from redis.connection import ConnectionPool
from typing import Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30

    @classmethod
    def from_env(cls) -> 'RedisConfig':
        return cls(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', '6379')),
            db=int(os.getenv('REDIS_DB', '0')),
            password=os.getenv('REDIS_PASSWORD'),
            max_connections=int(os.getenv('REDIS_MAX_CONNECTIONS', '20')),
            socket_timeout=float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0')),
            socket_connect_timeout=float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0')),
            retry_on_timeout=os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true',
            health_check_interval=int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '30')) 
        )


class RedisConnectionManager:
 
    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or RedisConfig.from_env()
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        
    def get_connection_pool(self) -> ConnectionPool:
        if self._pool is None:
            self._pool = ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval
            )
        return self._pool
    
    def get_client(self) -> redis.Redis:
        if self._client is None:
            pool = self.get_connection_pool()
            self._client = redis.Redis(connection_pool=pool, decode_responses=True)
        return self._client
    
    async def health_check(self) -> bool:
        try:
            client = self.get_client()
            response = client.ping()
            logger.debug(f"Redis health check: {response}")
            return response
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    def close(self):
        if self._client:
            self._client.close()
        if self._pool:
            self._pool.disconnect()

# Global connection manager instance
redis_manager = RedisConnectionManager()

