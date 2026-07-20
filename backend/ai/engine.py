import os
import threading
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
import torch
import logging

from .gpu_manager import gpu_manager

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  YOLOv8x — Best accuracy model for fixed CCTV person detection
# ═══════════════════════════════════════════════════════════════
BASE_MODEL_NAME  = 'yolov8x.engine'
INFER_IMGSZ      = 640             
INFER_CONF       = 0.10            
INFER_FPS        = 20              

current_dir = os.path.dirname(os.path.abspath(__file__))
PT_MODEL_PATH = os.path.normpath(os.path.join(current_dir, "..", "..", "models", BASE_MODEL_NAME))

_models_by_device = {}
_model_lock = threading.Lock()

def get_yolo_model_for_camera(camera_id, callback=None):
    """
    Returns a YOLO instance assigned to the best available GPU (or CPU)
    using the Adaptive GPU Load Balancer.
    """
    if not YOLO_AVAILABLE:
        return None
        
    device = gpu_manager.assign_camera(camera_id)
    
    with _model_lock:
        if device in _models_by_device:
            return _models_by_device[device]

        models_dir = os.path.normpath(os.path.join(current_dir, "..", "..", "models"))
        os.makedirs(models_dir, exist_ok=True)
        
        pt_path = os.path.normpath(os.path.join(models_dir, 'yolov8x.pt'))
        fallback_path = os.path.normpath(os.path.join(models_dir, 'yolov8n.pt'))
        
        # In a real environment, we'd compile the engine per-device.
        # For SentinelIQ, we will load the weights to the assigned device.
        load_path = pt_path if os.path.exists(pt_path) else fallback_path
        if not os.path.exists(load_path):
            try:
                # Auto-download from ultralytics if missing
                model = YOLO('yolov8n.pt') 
                load_path = fallback_path
            except Exception as e:
                logger.error(f"[AI ENGINE] Failed to download weights: {e}")
                return None
                
        logger.info(f"[AI ENGINE] Loading model {os.path.basename(load_path)} onto {device}")
        
        try:
            model = YOLO(load_path)
            model.to(device)
            if callback:
                model.add_callback("on_predict_start", callback)
            
            _models_by_device[device] = model
            return model
        except Exception as e:
            logger.error(f"[AI ENGINE ERROR] Failed to load model on {device}: {e}")
            return None
