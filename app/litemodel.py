import time
import logging
from pathlib import Path
from typing import List, Optional
import numpy as np
import onnxruntime as ort
from PIL import Image

from .config import get_settings
from .schemas import PredictionResult

logger = logging.getLogger(__name__)

class ModelPredictor:
    """
    Singleton class for ONNX model management.
    Ensures model is loaded once and reused across requests.
    """
    _instance: Optional['ModelPredictor'] = None
    _session: Optional[ort.InferenceSession] = None
    _class_names: List[str] = []
    _input_name: str = ""
    _input_height: int = 224
    _input_width: int = 224
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
        """Load ONNX model and class names from disk."""
        settings = get_settings()
        
        # 1. Validate Model Path
        model_path = Path(settings.model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
            
        # 2. Validate Class Names Path
        class_names_path = Path(getattr(settings, "class_names_path", "models/imagenet_classes.txt"))
        
        try:
            logger.info(f"Loading ONNX model from {model_path}")
            
            # Create Inference Session (CPU)
            self._session = ort.InferenceSession(str(model_path), providers=['CPUExecutionProvider'])
            
            # Get Input Details
            model_inputs = self._session.get_inputs()
            self._input_name = model_inputs[0].name
            shape = model_inputs[0].shape
            
            # Extract height/width (assuming [Batch, Channels, Height, Width])
            self._input_height = shape[2] if isinstance(shape[2], int) else 224
            self._input_width = shape[3] if isinstance(shape[3], int) else 224
            
            logger.info(f"Model expects input: {self._input_name} with shape {shape}")

            # Load Class Names
            if class_names_path.exists():
                with open(class_names_path, 'r') as f:
                    self._class_names = [line.strip() for line in f.readlines()]
                logger.info(f"Loaded {len(self._class_names)} class labels.")
            else:
                self._class_names = []
                logger.warning("No class labels loaded. Predictions will return indices.")

            self._model_loaded = True
            logger.info("Model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded and self._session is not None
    
    def predict(self, image: Image.Image) -> tuple[List[PredictionResult], float]:
        """
        Run prediction on image using ONNX Runtime.
        Uses PIL for preprocessing instead of OpenCV to save space.
        
        Args:
            image: PIL Image object
            
        Returns:
            Tuple of (predictions list, inference_time_ms)
        """
        if not self.is_loaded():
            raise RuntimeError("Model not loaded")
        
        settings = get_settings()
        start_time = time.time()
        
        # --- Preprocessing (Using PIL + Numpy) ---
        
        # 1. Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 2. Resize
        # using Image.BILINEAR to match standard YOLO/OpenCV behavior
        image_resized = image.resize((self._input_width, self._input_height), resample=Image.BILINEAR)
        
        # 3. Convert to Numpy and Normalize
        # np.array(pil_image) creates shape (Height, Width, 3)
        image_np = np.array(image_resized).astype(np.float32)
        input_data = image_np / 255.0
        
        # 4. Transpose (HWC -> CHW)
        input_data = np.transpose(input_data, (2, 0, 1))
        
        # 5. Add Batch Dimension
        input_data = np.expand_dims(input_data, axis=0)
        
        # --- Inference ---
        outputs = self._session.run(None, {self._input_name: input_data})
        
        inference_time = (time.time() - start_time) * 1000  # ms
        
        # --- Postprocessing ---
        
        # outputs[0] shape is [1, num_classes]
        predictions_raw = outputs[0][0] 
        
        # Get indices sorted by probability (descending)
        top_k = min(len(predictions_raw), settings.max_predictions)
        top_indices = np.argsort(predictions_raw)[::-1][:top_k]
        
        formatted_predictions = []
        
        for idx in top_indices:
            confidence = float(predictions_raw[idx])
            
            if confidence >= settings.model_confidence_threshold:
                label = self._class_names[idx] if idx < len(self._class_names) else str(idx)
                
                formatted_predictions.append(PredictionResult(
                    class_name=label,
                    confidence=round(confidence, 4)
                ))
        
        return formatted_predictions, inference_time
    
    def get_model_info(self) -> dict:
        """Get model metadata."""
        if not self.is_loaded():
            return {"loaded": False}
        
        return {
            "loaded": True,
            "type": "YOLO11l Classification (ONNX)",
            "num_classes": len(self._class_names),
            "input_shape": [1, 3, self._input_height, self._input_width]
        }

# Global instance
model_predictor = ModelPredictor()

# print(model_predictor.predict(Image.open("images/bus.jpg")))