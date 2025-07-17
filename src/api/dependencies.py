from typing import Generator

import redis
from fastapi import Depends

from src.config.settings import Settings, get_settings

def get_redis_client(settings: Settings = Depends(get_settings)) -> Generator:
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
    )

    try:
        client.ping()
        yield client
    finally:
        client.close()