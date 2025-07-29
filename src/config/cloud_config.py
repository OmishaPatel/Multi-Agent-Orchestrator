import os
from typing import Optional
from pydantic import BaseModel, Field

class CloudConfig(BaseModel):
    huggingface_api_token: Optional[str] = Field(default_factory=lambda: os.getenv("HUGGINGFACE_API_TOKEN"))

    huggingface_base_url: str = "https://api-inference.huggingface.co/models"
    request_timeout: float = 120.0

    def validate_api_token(self) -> bool:
        """Validate that API token is present"""
        return bool(self.huggingface_api_token)