import os
import threading
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
import torch

# ═══════════════════════════════════════════════════════════════
#  YOLOv8x — Best accuracy model for fixed CCTV person detection
#  86.7M parameters, highest mAP on COCO for person class
#  Compiles to TensorRT FP16 for real-time inference
# ═══════════════════════════════════════════════════════════════
BASE_MODEL_NAME  = 'yolov8x.engine'
INFER_IMGSZ      = 640             # Match TensorRT engine input size
INFER_CONF       = 0.10            # Lowered threshold to allow ByteTrack to capture hard-to-detect people
INFER_FPS        = 20              # Max inference fps per camera (GPU headroom)

current_dir = os.path.dirname(os.path.abspath(__file__))
PT_MODEL_PATH = os.path.normpath(os.path.join(current_dir, "..", "..", "models", BASE_MODEL_NAME))

_shared_yolo_model = None
_shared_model_lock = threading.Lock()
_export_lock = threading.Lock()
_is_compiling = False

def compile_engine_in_background(pt_path, engine_path, callback):
    """Compiles the TensorRT engine in a background thread and hot-swaps when completed."""
    global _is_compiling
    with _export_lock:
        if _is_compiling:
            return
        _is_compiling = True
        
    def export_worker():
        global _is_compiling, _shared_yolo_model
        try:
            print("[AI ENGINE] Loading base PyTorch model for background TensorRT export...")
            pt_model = YOLO(pt_path)
            print("[AI ENGINE] Compiling TensorRT FP16 Engine in background (imgsz=640, half=True, dynamic=False)...")
            pt_model.export(format="engine", imgsz=640, half=True, dynamic=False, device=0)
            print("[AI ENGINE] TensorRT engine export completed successfully in background.")
            
            # Hot-swap the model
            if os.path.exists(engine_path):
                print(f"[AI ENGINE] Dynamic Hot-Swap: Loading new TensorRT engine from {engine_path}...")
                new_model = YOLO(engine_path, task='detect')
                new_model.is_engine = True
                if callback:
                    new_model.add_callback("on_predict_start", callback)
                
                with _shared_model_lock:
                    _shared_yolo_model = new_model
                print("[AI ENGINE] Dynamic Hot-Swap Completed. Switched to TensorRT engine successfully!")
        except Exception as e:
            print(f"[AI ENGINE ERROR] Background TensorRT compilation failed: {e}")
        finally:
            with _export_lock:
                _is_compiling = False

    threading.Thread(target=export_worker, daemon=True).start()

def get_shared_yolo_model(on_predict_start_callback=None):
    """
    Returns a single shared YOLOv8x instance for all cameras.
    If the TensorRT engine exists, loads it immediately.
    If not, downloads YOLOv8x.pt from Ultralytics, starts background 
    TRT compilation, and falls back to PyTorch model for immediate inference.
    """
    global _shared_yolo_model
    if not YOLO_AVAILABLE:
        return None
        
    with _shared_model_lock:
        models_dir = os.path.normpath(os.path.join(current_dir, "..", "..", "models"))
        os.makedirs(models_dir, exist_ok=True)
        engine_path = os.path.normpath(os.path.join(models_dir, BASE_MODEL_NAME))
        pt_path = engine_path.replace('.engine', '.pt')

        if _shared_yolo_model is not None:
            # Check if engine file was compiled in background and we are still on fallback
            is_fallback = not getattr(_shared_yolo_model, 'is_engine', False)
            if is_fallback and os.path.exists(engine_path):
                try:
                    print(f"[AI ENGINE] Loading compiled TensorRT engine on-the-fly: {engine_path}")
                    new_model = YOLO(engine_path, task='detect')
                    new_model.is_engine = True
                    if on_predict_start_callback:
                        new_model.add_callback("on_predict_start", on_predict_start_callback)
                    _shared_yolo_model = new_model
                    print("[AI ENGINE] Dynamic Hot-Swap Completed successfully!")
                except Exception as e:
                    print(f"[AI ENGINE] Failed to hot-swap compiled engine: {e}")
            return _shared_yolo_model
            
        # 1. Primary Load: Try to load existing TensorRT engine
        if os.path.exists(engine_path):
            print(f"[AI ENGINE] Loading shared optimized TensorRT engine: {engine_path}")
            try:
                model = YOLO(engine_path, task='detect')
                model.is_engine = True
                if on_predict_start_callback:
                    model.add_callback("on_predict_start", on_predict_start_callback)
                _shared_yolo_model = model
                return _shared_yolo_model
            except Exception as e:
                print(f"[AI ENGINE] Failed to load existing engine: {e}. Falling back to PyTorch...")
        
        # 2. Fallback: Load PyTorch model (auto-downloads from Ultralytics if not present)
        if not os.path.exists(pt_path):
            print(f"[AI ENGINE] YOLOv8x weights not found. Downloading from Ultralytics...")
            # YOLO('yolov8x.pt') auto-downloads from Ultralytics hub
            try:
                model = YOLO('yolov8x.pt')
                # Save to our models directory
                import shutil
                downloaded_path = os.path.join(os.getcwd(), 'yolov8x.pt')
                if os.path.exists(downloaded_path) and downloaded_path != pt_path:
                    shutil.move(downloaded_path, pt_path)
                    print(f"[AI ENGINE] YOLOv8x weights saved to {pt_path}")
            except Exception as e:
                print(f"[AI ENGINE ERROR] Failed to download YOLOv8x: {e}")
                # Try loading any existing .pt file as fallback
                for fallback_name in ['yolov8l.pt', 'yolov8n.pt']:
                    fallback_path = os.path.normpath(os.path.join(models_dir, fallback_name))
                    if os.path.exists(fallback_path):
                        pt_path = fallback_path
                        print(f"[AI ENGINE] Using fallback model: {fallback_path}")
                        break

        if os.path.exists(pt_path):
            print(f"[AI ENGINE] Loading PyTorch model for immediate inference: {pt_path}")
            try:
                model = YOLO(pt_path)
                model.is_engine = False
                if torch.cuda.is_available():
                    model.to("cuda")
                if on_predict_start_callback:
                    model.add_callback("on_predict_start", on_predict_start_callback)
                _shared_yolo_model = model
                
                # Enable background compilation to build TensorRT FP16 engine
                compile_engine_in_background(pt_path, engine_path, on_predict_start_callback)
                return _shared_yolo_model
            except Exception as e:
                print(f"[AI ENGINE ERROR] Failed to load PyTorch fallback: {e}")
                
        # If PT doesn't exist, try ONNX fallback
        onnx_path = engine_path.replace('.engine', '.onnx')
        if os.path.exists(onnx_path):
            print(f"[AI ENGINE] Loading ONNX model for immediate fallback: {onnx_path}")
            try:
                model = YOLO(onnx_path)
                model.is_engine = False
                if on_predict_start_callback:
                    model.add_callback("on_predict_start", on_predict_start_callback)
                _shared_yolo_model = model
                return _shared_yolo_model
            except Exception as e:
                print(f"[AI ENGINE ERROR] Failed to load ONNX fallback: {e}")
                
        raise RuntimeError("CRITICAL: No model (TensorRT, PyTorch .pt, or ONNX) could be found in models/ directory.")

def get_yolo_model_for_camera(camera_id, callback=None):
    return get_shared_yolo_model(callback)
