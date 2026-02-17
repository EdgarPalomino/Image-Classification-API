import time
from pathlib import Path
from typing import List, Optional
import numpy as np
from PIL import Image
from ultralytics import YOLO
from .config import get_settings
from .schemas import PredictionResult
import logging
import cv2

logger = logging.getLogger(__name__)

class ModelPredictor:
    """
    Singleton class for YOLO model management.
    Ensures model is loaded once and reused across requests.
    """
    _instance: Optional['ModelPredictor'] = None
    _model: Optional[YOLO] = None
    _model_loaded: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize on first creation only."""
        if not self._model_loaded:
            self._load_model()
    
    def _load_model(self):
        """Load YOLO model from disk."""
        settings = get_settings()
        model_path = Path(settings.model_path)
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        try:
            logger.info(f"Loading model from {model_path}")
            self._model = YOLO(str(model_path))
            self._model_loaded = True
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded and self._model is not None
    
    def predict(self, image: Image.Image) -> tuple[List[PredictionResult], float]:
        """
        Run prediction on image.
        
        Args:
            image: PIL Image object
            
        Returns:
            Tuple of (predictions list, inference_time_ms)
        """
        if not self.is_loaded():
            raise RuntimeError("Model not loaded")
        
        settings = get_settings()
        
        # Time the inference
        start_time = time.time()
        
        # Run prediction
        results = self._model(image, verbose=False)
        
        inference_time = (time.time() - start_time) * 1000  # Convert to ms
        
        # Parse results
        predictions = []
        for r in results:
            top_indices = r.probs.top5
            top_confidences = r.probs.top5conf
            class_names = r.names
            
            # Limit to max_predictions
            for i in range(min(len(top_indices), settings.max_predictions)):
                class_idx = top_indices[i]
                confidence = float(top_confidences[i].item())
                
                # Filter by confidence threshold
                if confidence >= settings.model_confidence_threshold:
                    predictions.append(PredictionResult(
                        class_name=class_names[class_idx],
                        confidence=round(confidence, 4)
                    ))
        
        return predictions, inference_time
    
    def get_model_info(self) -> dict:
        """Get model metadata."""
        if not self.is_loaded():
            return {"loaded": False}
        
        return {
            "loaded": True,
            "type": "YOLO11l Classification",
            "num_classes": len(self._model.names) if hasattr(self._model, 'names') else "unknown"
        }

# Global instance
model_predictor = ModelPredictor()