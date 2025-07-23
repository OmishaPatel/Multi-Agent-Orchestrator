from dataclasses import dataclass
from src.config.settings import get_settings

@dataclass
class CleanupConfig:
    """Configuration for background cleanup service"""
    
    # How often to run cleanup (hours)
    cleanup_interval_hours: int
    
    # Maximum age before deletion (hours)
    max_age_hours: int
    
    # Enable/disable cleanup service
    cleanup_enabled: bool
    
    @classmethod
    def from_env(cls) -> 'CleanupConfig':
        """Create configuration from centralized settings"""
        settings = get_settings()
        return cls(
            cleanup_interval_hours=settings.CLEANUP_INTERVAL_HOURS,
            max_age_hours=settings.CLEANUP_MAX_AGE_HOURS,
            cleanup_enabled=settings.CLEANUP_ENABLED
        )