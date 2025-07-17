import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health, workflow
from src.config.settings import get_settings

def create_application() -> FastAPI:

    settings = get_settings()

    application = FastAPI(
        title="Clarity.ai API",
        description="Multi-agent task orchestration system API",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
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