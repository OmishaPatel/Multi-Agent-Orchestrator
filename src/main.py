import uvicorn
import logging
import signal
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.api.routes import health, workflow
from src.config.settings import get_settings
from src.utils.logging_config import setup_logging, get_logger
from src.core.background_cleanup import cleanup_service

# Initialize logging first
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down...")
    cleanup_service.shutdown()
    sys.exit(0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    #starup
    logger.info("Starting Clarity.ai application")
    
    # Register signal handlers after startup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        cleanup_service.start()
        logger.info("Background cleanup service started")
    except Exception as e:
        logger.error(f"Failed to start cleanup service: {e}")

    yield

    #shutdown
    logger.info("Shutting down Clarity.ai application")

    # stop background cleanup service
    try:
        cleanup_service.stop()
        logger.info("Background cleanup service stopped")
    except Exception as e:
        logger.error(f"Error stopping cleanup service: {e}")


def create_application() -> FastAPI:

    settings = get_settings()

    application = FastAPI(
        title="Clarity.ai API",
        description="Multi-agent task orchestration system API",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins= settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, tags=["health"])
    application.include_router(workflow.router, prefix="/api/v1", tags=["Workflow"])

    return application

app = create_application()

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)