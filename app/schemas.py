from pydantic import BaseModel, Field
from typing import List, Optional

class PredictionResult(BaseModel):
    """Single prediction result."""
    class_name: str = Field(..., description="Predicted class name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence (0-1)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "class_name": "bolete_mushroom",
                "confidence": 0.8542
            }
        }

class PredictionResponse(BaseModel):
    """API response containing predictions."""
    success: bool = Field(default=True)
    predictions: List[PredictionResult]
    model_version: str = Field(..., description="Model version used")
    inference_time_ms: float = Field(..., description="Time taken for inference in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "predictions": [
                    {"class_name": "golden_retriever", "confidence": 0.92},
                    {"class_name": "labrador", "confidence": 0.05}
                ],
                "model_version": "yolo11l-cls",
                "inference_time_ms": 145.23
            }
        }

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_loaded: bool
    model_path: str
    uptime_seconds: float

class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None