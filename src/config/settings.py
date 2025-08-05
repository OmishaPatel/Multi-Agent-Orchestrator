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

    # LLM Integration Configuration
    HUGGINGFACE_API_TOKEN: str = Field("", description="Hugging Face API token")
    
    # Ollama Configuration
    OLLAMA_BASE_URL: str = Field("http://localhost:11434", description="Ollama base URL")
    OLLAMA_TIMEOUT: int = Field(60, description="Ollama request timeout in seconds")
    TEST_OLLAMA: bool = Field(True, description="Enable Ollama testing")
    
    # vLLM Configuration
    VLLM_BASE_URL: str = Field("http://localhost:8000", description="vLLM base URL")
    VLLM_API_KEY: str = Field("dummy-key", description="vLLM API key")
    TEST_VLLM: bool = Field(False, description="Enable vLLM testing")
    
    # Test Configuration
    TEST_TIMEOUT: int = Field(60, description="Test timeout in seconds")

    # Simple LLM Cache Configuration
    LLM_CACHE_ENABLED: bool = Field(True, description="Enable basic LLM response caching")
    LLM_CACHE_MAX_SIZE: int = Field(100, description="Maximum number of cached responses")
    
    # Redis Configuration
    REDIS_ENABLED: bool = Field(True, description="Enable Redis checkpointing (disable for local testing)")
    ENABLE_CHECKPOINTING: bool = Field(True, description="Enable workflow checkpointing (uses memory if Redis disabled)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()