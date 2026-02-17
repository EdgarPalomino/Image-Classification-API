from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "ML Prediction API"
    app_version: str = "0.1.0"
    debug: bool = True
    
    # Model Settings
    model_path: str = "./models/yolo11l-cls.onnx"
    class_names_path: str = "./models/imagenet_classes.txt" 
    model_confidence_threshold: float = 0.25
    max_predictions: int = 5
    
    # API Settings
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    allowed_extensions: set = {".jpg", ".jpeg", ".png", ".webp"}
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1  
    
    # Monitoring
    enable_metrics: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """Cache settings to avoid re-reading env vars on every call."""
    return Settings()