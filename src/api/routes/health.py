from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.config.settings import Settings, get_settings
from src.config.redis_config import redis_manager


router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str

class StatusResponse(BaseModel):
    status: str
    environment: str
    version: str
    redis_connected: bool

@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)):
    return{
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
    }


@router.get("/health/status", response_model=StatusResponse)
async def status_check(settings: Settings = Depends(get_settings)):
    redis_connected = await redis_manager.health_check()

    overall_status = "ok" if redis_connected else "degraded"

    return{
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
        "redis_connected": redis_connected,
    }