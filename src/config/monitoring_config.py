from pydantic import BaseSettings

class SimpleMonitoringConfig(BaseSettings):    
    # Basic monitoring settings
    MONITORING_ENABLED: bool = True
    MONITORING_STORAGE_PATH: str = "data/monitoring"
    MAX_METRICS_MEMORY: int = 1000
    DRIFT_DETECTION_WINDOW: int = 50
    
    # Simple alert thresholds
    HIGH_CPU_THRESHOLD: float = 80.0  # 80%
    HIGH_MEMORY_THRESHOLD: float = 85.0  # 85%
    HIGH_ERROR_RATE_THRESHOLD: float = 0.2  # 20%
    
    # MLflow settings (optional)
    MLFLOW_ENABLED: bool = False
    MLFLOW_EXPERIMENT_NAME: str = "clarity-ai"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

def get_simple_monitoring_config() -> SimpleMonitoringConfig:
    return SimpleMonitoringConfig()
