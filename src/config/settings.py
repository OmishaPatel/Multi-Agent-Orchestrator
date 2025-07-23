from functools import lru_cache
from typing import List, Optional, Union

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    ENVIRONMENT: str = Field("development", description="Environment (development, testing, production)")
    DEBUG: bool = Field(False, description="Debug mode")
    API_PREFIX: str = Field("/api/v1", description="API prefix")
    OPENAI_API_KEY: str = Field("", description="Open AI api key")
    TAVILY_API_KEY: str = Field("", description="Tavily api key")
    
    CORS_ORIGINS: List[Union[str, AnyHttpUrl]] = Field(
        ["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins"
    )

    REDIS_HOST: str = Field("localhost", description="Redis Host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_DB: int = Field(0, description="Redis database")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis password")

    DEFAULT_MODEL: str = Field("phi3:mini", description="Default LLM model for development")
    
    # Cleanup service settings
    CLEANUP_ENABLED: bool = Field(True, description="Enable background cleanup service")
    CLEANUP_INTERVAL_HOURS: int = Field(6, description="Cleanup interval in hours")
    CLEANUP_MAX_AGE_HOURS: int = Field(24, description="Maximum age before deletion in hours")

    # Logging settings
    LOG_LEVEL: str = Field("INFO", description="Default log level (DEBUG, INFO, WARNING, ERROR)")
    QUIET_TERMINAL: bool = Field(True, description="Minimize logs in terminal")
    VERBOSE_LOGGING: bool = Field(False, description="Set logging verbosity level")
    CLEANUP_LOG_LEVEL: str = Field("WARNING", description="Log level for cleanup service")
    ENABLE_FILE_LOGGING: bool = Field(True, description="Enable logging to files")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()