import cv2
import time
import os
import queue
import threading
import numpy as np
import asyncio
from backend.core import state
import torch
# ─── RTSP Connections Core ─────────────────────────────────────────

from backend.ai.calibration_config import map_video_to_leaflet
from backend.ai.tracker import WorkerTracker

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    import lap
    BYTETRACK_AVAILABLE = True
except ImportError:
    BYTETRACK_AVAILABLE = False
    print("[AI ENGINE] 'lap' not found — ByteTrack disabled.")

from backend.core.config_loader import loader

current_dir = os.path.dirname(os.path.abspath(__file__))

BASE_MODEL_NAME  = 'yolov8l.pt'   
INFER_IMGSZ      = 672            
INFER_CONF       = 0.25           
DISPLAY_FPS      = 30             
TARGET_INFER_FPS = 24

PT_MODEL_PATH = os.path.abspath(os.path.join(current_dir, "..", "..", "models", BASE_MODEL_NAME))

# ─── ASYMMETRIC BATCH MULTIPLEXER STRUCTURES ─────────────────────
# Global cache for full-resolution raw uncompressed frames (camera_id -> frame)
latest_raw_frames = {}
latest_raw_frames_lock = threading.Lock()

# Central thread-safe frame queue with maxsize safeguard to prevent VRAM/RAM bloating
frame_queue = queue.Queue(maxsize=100)

_active_engines = {}
_engines_lock = threading.Lock()

active_gate_cameras = set()

_yolo_models = {}
_yolo_models_lock = threading.Lock()
_gpu_inference_lock = threading.Lock()

# Per-camera inference image size (TensorRT engines have fixed compiled sizes)
_model_imgsz = {}  # camera_id -> int

# Priority order to try when CUDA is available.
# yolov8m = good balance of accuracy + speed for plant CCTV with many people.
_TENSORRT_ENGINE_PRIORITY = [
    'yolov8m.engine',   # Medium — accurate, fast, recommended for multi-person scenes
    'yolov8l.engine',   # Large  — higher accuracy, use if GPU has enough VRAM
    'yolov8n.engine',   # Nano   — last resort; fast but fluctuates in crowds
]

def get_yolo_model(camera_id):
    with _yolo_models_lock:
        if camera_id not in _yolo_models:
            if not YOLO_AVAILABLE:
                return None
            try:
                cuda = torch.cuda.is_available()
                loaded = False

                # ── Try TensorRT engines first if tensorrt is installed ─────────
                try:
                    import tensorrt
                    tensorrt_available = True
                except ImportError:
                    tensorrt_available = False

                if cuda and tensorrt_available:
                    for engine_name in _TENSORRT_ENGINE_PRIORITY:
                        engine_path = os.path.abspath(
                            os.path.join(current_dir, "..", "..", "models", engine_name)
                        )
                        if os.path.exists(engine_path):
                            try:
                                model = YOLO(engine_path)
                                _yolo_models[camera_id] = model
                                # Read compiled imgsz from the engine metadata
                                try:
                                    compiled_sz = model.overrides.get('imgsz', INFER_IMGSZ)
                                    if isinstance(compiled_sz, (list, tuple)):
                                        compiled_sz = compiled_sz[0]
                                    _model_imgsz[camera_id] = int(compiled_sz)
                                except Exception:
                                    _model_imgsz[camera_id] = INFER_IMGSZ
                                print(f"[AI ENGINE] TensorRT loaded: {engine_name} (imgsz={_model_imgsz[camera_id]}) for cam {camera_id}")
                                loaded = True
                                break
                            except Exception as eng_err:
                                print(f"[AI ENGINE] Engine {engine_name} failed: {eng_err}")

                # ── Fall back to PyTorch .pt model ────────────────────────────
                if not loaded:
                    pt_path = PT_MODEL_PATH if os.path.exists(PT_MODEL_PATH) else BASE_MODEL_NAME
                    _yolo_models[camera_id] = YOLO(pt_path)
                    _model_imgsz[camera_id] = INFER_IMGSZ
                    print(f"[AI ENGINE] PyTorch model loaded: {pt_path} for cam {camera_id}")

            except Exception as e:
                print(f"[AI ENGINE ERROR] Failed to load model for cam {camera_id}: {e}")
                return None

        return _yolo_models.get(camera_id)

class StreamEngine:
    def __init__(self, camera_id, source, detect_people=False):
        self.camera_id = str(camera_id)
        self.source = source
        self.cap = None

        self.latest_frame = None
        self.cached_boxes = []    
        self.person_count = 0
        self.is_running = True
        self.frame_lock = threading.Lock()
        self.latest_frame_jpeg = None
        self.latest_ai_jpeg = None
        self._frame_seq = 0  # incremented every time a new frame is captured
        self.stream_clients = 0
        self.background_tracking = False
        self.tracker = WorkerTracker()

        cuda = torch.cuda.is_available()
        self.device_target = 0 if cuda else "cpu"
        self.use_fp16 = cuda     

        self.model = get_yolo_model(self.camera_id) if detect_people else None
        self.inference_started = detect_people
        self.detect_people = detect_people

        self.last_people_log_time = 0
        self.last_people_count = -1
        self.last_posture_log_time = 0

        from backend.stream.event_manager import EventManager
        self.event_manager = EventManager(self.camera_id)
        self.gate_counting = False
        self.gate_in_count = 0
        self.gate_out_count = 0

        # Start OpenCV capture loop
        threading.Thread(target=self._producer_loop, daemon=True).start()

    def _producer_loop(self):
        print(f"[PRODUCER] Started for camera {self.camera_id} at {self.source}")
        if self.source is None or self.source == "":
            print(f"[PRODUCER ERROR] Source URL is None or empty for camera {self.camera_id}. Aborting capture.")
            self.is_running = False
            return

        is_rtsp = isinstance(self.source, str) and (
            self.source.startswith("rtsp://") or self.source.startswith("rtsps://")
        )

        # Open capture — use native backend; avoid FFMPEG env vars which race across threads
        if is_rtsp:
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            if self.cap and self.cap.isOpened():
                # Minimal RTSP buffer: hold only 1 frame in queue
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            self.cap = cv2.VideoCapture(self.source)

        # RTSP fallback to local test video
        if (self.cap is None or not self.cap.isOpened()) and is_rtsp:
            print(f"[PRODUCER] RTSP failed, falling back to local test video...")
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            fallback_videos = {
                "27": "people_detection.mp4",
                "28": "people_palace.mp4",
                "3": "one_by_one.mp4",
                "33": "person_bicycle_car.mp4",
                "35": "classroom.mp4",
                "113": "fall.mp4",
                "124": "store_aisle.mp4",
                "107": "gas_leak_panic.mp4"
            }
            v_name = fallback_videos.get(str(self.camera_id), "people_detection.mp4")
            video_path = os.path.normpath(os.path.join(base_dir, "test_video", v_name))
            if os.path.exists(video_path):
                self.source = video_path
                is_rtsp = False
                self.cap = cv2.VideoCapture(self.source)
                if self.cap is not None and self.cap.isOpened():
                    print(f"[PRODUCER] Offline fallback successful: {video_path}")
                else:
                    print(f"[PRODUCER ERROR] Fallback video also failed: {video_path}")
                    self.is_running = False
                    return
            else:
                print(f"[PRODUCER ERROR] Fallback video not found: {video_path}")
                self.is_running = False
                return

        if self.cap is None or not self.cap.isOpened():
            print(f"[PRODUCER ERROR] Could not open: {self.source}")
            self.is_running = False
            return

        # Detect local file — throttle read to native FPS so we don't flood memory
        is_file = not is_rtsp
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 120:
            fps = 25.0
        frame_delay = 1.0 / fps

        print(f"[PRODUCER] Camera {self.camera_id} opened. fps={fps:.1f}, is_file={is_file}")

        try:
            while self.is_running:
                t_start = time.time()

                if is_file:
                    # Local file: read sequentially at native FPS
                    ret, frame = self.cap.read()
                    if not ret:
                        # Loop the video
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                else:
                    # RTSP: drain the internal buffer by grabbing without decoding,
                    # then decode only the very latest frame — this is the key to zero latency
                    grabbed = False
                    for _ in range(5):
                        g = self.cap.grab()
                        if g:
                            grabbed = True
                        else:
                            break
                    if not grabbed:
                        time.sleep(0.1)
                        continue
                    ret, frame = self.cap.retrieve()
                    if not ret or frame is None:
                        time.sleep(0.05)
                        continue

                if frame is not None:
                    h, w = frame.shape[:2]
                    if w > 640 or h > 360:
                        frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
                    with self.frame_lock:
                        self.latest_frame = frame
                        ret_jpg, buffer_jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                        if ret_jpg:
                            self.latest_frame_jpeg = buffer_jpg.tobytes()
                        self._frame_seq += 1

                if is_file:
                    elapsed = time.time() - t_start
                    sleep_time = frame_delay - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                # For RTSP: no sleep — grab loop already acts as pacing

        finally:
            if self.cap:
                self.cap.release()

    def _inference_loop(self):
        # Wait for the first frame to load to minimize connection delay
        while self.is_running and self.latest_frame is None:
            time.sleep(0.05)
        frame_interval = 1.0 / TARGET_INFER_FPS if 'TARGET_INFER_FPS' in globals() else 1.0 / 30.0

        while self.is_running:
            t_start = time.time()

            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None

            if frame is not None and self.model is not None and (self.detect_people or self.background_tracking or self.gate_counting):
                try:
                    active_mods = state.get_ai_modules(self.camera_id)
                    frame_h, frame_w = frame.shape[:2]

                    # Use per-camera imgsz — TensorRT engines have a fixed compiled size
                    cam_imgsz = _model_imgsz.get(self.camera_id, INFER_IMGSZ)
                    tracker_yaml = "bytetrack.yaml" if BYTETRACK_AVAILABLE else "botsort.yaml"
                    with _gpu_inference_lock:
                        results = self.model.track(frame, classes=[0], imgsz=cam_imgsz, conf=INFER_CONF,
                            verbose=False, tracker=tracker_yaml,
                            persist=True, device=self.device_target)[0]

                    temp_boxes = []
                    tracked_positions = []
                    active_tids = set()
                    
                    self.tracker.cleanup()

                    # Call standalone accuracy optimizer module
                    from backend.ai.model_optimizer import optimize_detections
                    optimized_boxes = optimize_detections(results)

                    # No ReID tracking; purely stateless bounding boxes

                    now = time.time()
                    frame_data_for_rules = []
                    for (x1, y1, x2, y2, conf, tid, kpts) in optimized_boxes:
                        temp_boxes.append((x1, y1, x2, y2, conf, tid))
                        if tid != -1:
                            active_tids.add(tid)
                            frame_data_for_rules.append({
                                'track_id': str(tid),
                                'class_name': 'person',
                                'bbox': [x1, y1, x2, y2],
                                'timestamp': now
                            })

                            # --- Spatial-Temporal Tracking Logic ---
                            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                            from backend.core.state import get_worker_state, set_worker_state
                            worker_data = get_worker_state(self.camera_id, tid)
                            prev_cx, prev_cy = worker_data.get('centroid') or (cx, cy)
                            
                            # Append to bboxes history
                            bboxes_history = worker_data.get('bboxes', [])
                            bboxes_history.append([x1, y1, x2, y2])
                            if len(bboxes_history) > 120:
                                bboxes_history.pop(0)
                                
                            # EMA Smoothing to prevent UI dots from fluctuating
                            alpha = 0.3
                            prev_smooth_cx = worker_data.get('smooth_cx', cx)
                            prev_smooth_y2 = worker_data.get('smooth_y2', y2)
                            
                            smooth_cx = alpha * cx + (1 - alpha) * prev_smooth_cx
                            smooth_y2 = alpha * y2 + (1 - alpha) * prev_smooth_y2
                            
                            # Calculate spatial velocity (distance moved)
                            dist = ((cx - prev_cx)**2 + (cy - prev_cy)**2) ** 0.5
                            
                            # ---------------------------------------------
                            
                            now = time.time()
                            state_val = worker_data.get('state', 'MOVING')
                            stationary_since = worker_data.get('stationary_since')
                            
                            # 15 pixel radius threshold
                            if dist > 15.0:
                                # Moving fluidly -> reset state
                                set_worker_state(self.camera_id, tid, {
                                    'state': 'MOVING',
                                    'centroid': (cx, cy),
                                    'smooth_cx': smooth_cx,
                                    'smooth_y2': smooth_y2,
                                    'stationary_since': None,
                                    'bboxes': bboxes_history
                                })
                            else:
                                # Still stationary
                                if stationary_since is None:
                                    set_worker_state(self.camera_id, tid, {'centroid': (cx, cy), 'smooth_cx': smooth_cx, 'smooth_y2': smooth_y2, 'stationary_since': now, 'bboxes': bboxes_history})
                                else:
                                    if now - stationary_since > 15.0 and state_val != 'IDLE':
                                        # >15s stationary -> POTENTIAL_STATIONARY -> Trigger validation funnel
                                        set_worker_state(self.camera_id, tid, {'state': 'POTENTIAL_STATIONARY', 'bboxes': bboxes_history})
                                        # Trigger Tier 1
                                        active_mods = state.get_ai_modules(self.camera_id)
                                        if active_mods and 'productivity' in active_mods:
                                            from backend.ai.vlm_integration import enqueue_vlm_task
                                            enqueue_vlm_task(
                                                camera_id=self.camera_id,
                                                use_case='STATIONARY_WORKER',
                                                frame=frame,
                                                box=(x1, y1, x2, y2),
                                                tid=tid,
                                                prompt='Person standing completely still for over 15 seconds.',
                                                severity='WARNING',
                                                track_history=bboxes_history
                                            )

                            from backend.ai.calibration_config import map_video_to_leaflet, map_blueprint_to_gps

                            bp_coord = map_video_to_leaflet(self.camera_id, smooth_cx, smooth_y2, frame_w, frame_h)
                            if bp_coord:
                                lat_lng = map_blueprint_to_gps(self.camera_id, bp_coord[0], bp_coord[1])
                            else:
                                bp_coord = [0, 0]
                                lat_lng  = [0, 0]

                            tracked_positions.append({
                                'x': float(cx), 'y': float(cy), 
                                'tid': int(tid),
                                'pos': [float(lat_lng[0]), float(lat_lng[1])],
                                'blueprint_pos': [float(bp_coord[0]), float(bp_coord[1])]
                            })

                    # --- Perimeter Wall Climbing Engine ---
                    if active_mods and 'perimeter' in active_mods:
                        from backend.ai.perimeter_guard import detect_wall_climb
                        from backend.core.state import worker_states
                        camera_tracks = worker_states.get(self.camera_id, {})
                        # Define a virtual wall perimeter zone in frame coordinates (expanded for test video)
                        climb_alerts = detect_wall_climb(camera_tracks, self.camera_id, wall_y_bounds=(0, 1080))
                        if climb_alerts:
                            from backend.core.state import add_alert_log
                            for alert in climb_alerts:
                                log_entry = add_alert_log(
                                    camera_id=self.camera_id,
                                    camera_name="Perimeter Cam",
                                    event_type=alert["type"],
                                    severity=alert["severity"],
                                    details=alert["details"],
                                    evidence_file="",
                                    vlm_status="PENDING"
                                )

                                # Optional VLM Validation
                                from backend.ai.vlm_integration import enqueue_vlm_task
                                enqueue_vlm_task(
                                    camera_id=self.camera_id,
                                    use_case=alert['type'],
                                    frame=frame,
                                    box=None if alert.get('vlm_use_full_frame') else alert.get('bbox'),
                                    tid=alert['track_id'],
                                    prompt=alert['vlm_prompt'],
                                    severity=alert['severity'],
                                    alert_id=log_entry['id'],
                                    track_history=camera_tracks.get(alert['track_id'], {}).get('bboxes', [])
                                )

                    if active_mods:
                        now = time.time()
                        cam_info = loader.get_camera_details(self.camera_id)
                        cam_name = cam_info.get("Name", f"Cam {self.camera_id}") if cam_info else f"Cam {self.camera_id}"
                        from backend.ai.vlm_integration import enqueue_vlm_task
                        from backend.core.state import add_real_log

                        # 1. YOLO People Counting → log to AI channel
                        if 'people' in active_mods:
                            if self.person_count != self.last_people_count or (now - self.last_people_log_time) >= 10.0:
                                self.last_people_log_time = now
                                self.last_people_count = self.person_count
                                add_real_log(
                                    self.camera_id, cam_name, "PEOPLE_COUNT", "INFO",
                                    f"[People Counting] {self.person_count} worker(s) detected on {cam_name}."
                                )


                    self.cached_boxes = temp_boxes
                    self.person_count = len(temp_boxes)

                    # Pre-draw boxes and encode self.latest_ai_jpeg to cache
                    display_frame = frame.copy()
                    from backend.core.state import get_highlighted_tids
                    active_alerts = get_highlighted_tids(self.camera_id)
                    for (x1, y1, x2, y2, conf, tid) in temp_boxes:
                        is_target = (tid in active_alerts)
                        if is_target:
                            color = (0, 140, 255)  # Safety Orange / Amber (BGR)
                            thickness = 3
                            label = f"#{tid} [VLM ALERT]"
                        else:
                            color = (0, 255, 0)
                            thickness = 2
                            label = f"#{tid}" if tid != -1 else ""
                            
                        cv2.rectangle(display_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
                        text_str = f"WORKER {label}"
                        (text_w, text_h), _ = cv2.getTextSize(text_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                        cv2.rectangle(display_frame, (int(x1), int(y1) - text_h - 8), (int(x1) + text_w + 4, int(y1)), color, -1)
                        cv2.putText(display_frame, text_str, (int(x1) + 2, int(y1) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0) if is_target else (255, 255, 255), 1)

                    ret_ai, buffer_ai = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    if ret_ai:
                        with self.frame_lock:
                            self.latest_ai_jpeg = buffer_ai.tobytes()

                    if hasattr(state, 'state_lock'):
                        with state.state_lock:
                            if not isinstance(state.shared_stats, dict):
                                state.shared_stats = {"cameras": []}
                            if "cameras" not in state.shared_stats:
                                state.shared_stats["cameras"] = []
                                
                            found = False
                            for c in state.shared_stats["cameras"]:
                                if c.get("id") == self.camera_id:
                                    c["person_count"] = self.person_count if self.background_tracking else 0
                                    c["tracked_positions"] = tracked_positions if self.background_tracking else []
                                    found = True
                                    break
                            if not found:
                                state.shared_stats["cameras"].append({
                                    "id": self.camera_id,
                                    "person_count": self.person_count if self.background_tracking else 0,
                                    "tracked_positions": tracked_positions if self.background_tracking else []
                                })
                            # Update top-level person_count aggregate
                            state.shared_stats["person_count"] = sum(
                                c.get("person_count", 0) for c in state.shared_stats["cameras"]
                            )

                    # Submit to decoupled Event Rules Engine
                    from backend.workers.event_worker import submit_event_task
                    submit_event_task(self, frame_data_for_rules, frame, tracked_positions)

                except Exception as e:
                    print(f"[INFERENCE ERROR] {e}")

            elapsed = time.time() - t_start
            time.sleep(max(0.001, frame_interval - elapsed))

    def get_worker_from_click(self, click_x_norm, click_y_norm):
        with self.frame_lock:
            if not self.cached_boxes: return -1
            
            # Map normalized coordinates to pixel coordinates (assuming 640x360 internal size)
            click_x = click_x_norm * 640
            click_y = click_y_norm * 360

            closest_tid = -1
            min_dist = float('inf')

            for (x1, y1, x2, y2, conf, tid) in self.cached_boxes:
                if tid == -1: continue
                # First check if click is strictly inside the box
                if x1 <= click_x <= x2 and y1 <= click_y <= y2:
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    dist = (cx - click_x)**2 + (cy - click_y)**2
                    if dist < min_dist:
                        min_dist = dist
                        closest_tid = tid
            
            # If nothing clicked inside bounding box, do a loose distance check to centroids
            if closest_tid == -1:
                for (x1, y1, x2, y2, conf, tid) in self.cached_boxes:
                    if tid == -1: continue
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    dist = (cx - click_x)**2 + (cy - click_y)**2
                    # 50 pixel radius forgiveness
                    if dist < 2500 and dist < min_dist:
                        min_dist = dist
                        closest_tid = tid

            return closest_tid

    def generate_frames(self, draw_boxes=False, selected_worker=''):
        self.stream_clients += 1
        frame_interval = 1.0 / DISPLAY_FPS
        
        # Calculate if the currently selected worker belongs to this feed
        selected_tid = -1
        if selected_worker and '-' in selected_worker:
            parts = selected_worker.split('-')
            if parts[0] == self.camera_id:
                try:
                    selected_tid = int(parts[1])
                except ValueError:
                    pass

        try:
            while self.is_running:
                t_start = time.time()
                
                # Check pre-encoded JPEGs first to reduce CPU overhead
                use_cache = False
                cached_bytes = None
                with self.frame_lock:
                    if not draw_boxes and self.latest_frame_jpeg is not None:
                        cached_bytes = self.latest_frame_jpeg
                        use_cache = True
                    elif draw_boxes and selected_tid == -1 and self.latest_ai_jpeg is not None:
                        cached_bytes = self.latest_ai_jpeg
                        use_cache = True
                        
                if use_cache and cached_bytes:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + cached_bytes + b'\r\n')
                    elapsed = time.time() - t_start
                    time.sleep(max(0.001, frame_interval - elapsed))
                    continue

                with self.frame_lock:
                    display_frame = self.latest_frame.copy() if self.latest_frame is not None else None

                if display_frame is None:
                    # Yield a blank placeholder if stream is down
                    blank = np.zeros((360, 640, 3), dtype=np.uint8)
                    cv2.putText(blank, "CAMERA OFFLINE / CONNECTING...", (120, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    ret, buffer = cv2.imencode('.jpg', blank, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    if ret:
                        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    time.sleep(0.5)
                    continue

                if draw_boxes:
                    from backend.core.state import get_highlighted_tids
                    active_alerts = get_highlighted_tids(self.camera_id)
                    
                    for (x1, y1, x2, y2, conf, tid) in self.cached_boxes:
                        is_target = (tid == selected_tid and tid != -1) or (tid in active_alerts)
                        
                        # Apply vibrant orange indicator styling if target is highlighted
                        if is_target:
                            color = (0, 140, 255)  # Safety Orange / Amber (BGR)
                            thickness = 3
                            label = f"#{tid} [VLM ALERT]"
                        else:
                            color = (0, 255, 0)
                            thickness = 2
                            label = f"#{tid}" if tid != -1 else ""
                            
                        cv2.rectangle(display_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
                        
                        # High-contrast premium text badge
                        text_str = f"WORKER {label}"
                        (text_w, text_h), _ = cv2.getTextSize(text_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                        cv2.rectangle(display_frame, (int(x1), int(y1) - text_h - 8), (int(x1) + text_w + 4, int(y1)), color, -1)
                        cv2.putText(display_frame, text_str, (int(x1) + 2, int(y1) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0) if is_target else (255, 255, 255), 1)

                ret, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ret:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

                elapsed = time.time() - t_start
                time.sleep(max(0.001, frame_interval - elapsed))
        finally:
            self.stream_clients -= 1
            self.check_shutdown()

    async def generate_frames_async(self, draw_boxes=False, selected_worker=''):
        self.stream_clients += 1
        frame_interval = 1.0 / DISPLAY_FPS
        
        selected_tid = -1
        if selected_worker and '-' in selected_worker:
            parts = selected_worker.split('-')
            if parts[0] == self.camera_id:
                try:
                    selected_tid = int(parts[1])
                except ValueError:
                    pass

        last_seq = -1

        try:
            while self.is_running:
                t_start = time.time()

                # Wait up to frame_interval for a new frame, polling every 5ms
                deadline = t_start + frame_interval
                while True:
                    with self.frame_lock:
                        cur_seq = self._frame_seq
                    if cur_seq != last_seq:
                        break
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(0.005, remaining))

                # Check pre-encoded JPEGs first
                cached_bytes = None
                with self.frame_lock:
                    cur_seq = self._frame_seq
                    if not draw_boxes and self.latest_frame_jpeg is not None:
                        cached_bytes = self.latest_frame_jpeg
                    elif draw_boxes and selected_tid == -1 and self.latest_ai_jpeg is not None:
                        cached_bytes = self.latest_ai_jpeg

                if cached_bytes and cur_seq != last_seq:
                    last_seq = cur_seq
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + cached_bytes + b'\r\n')
                    continue

                with self.frame_lock:
                    display_frame = self.latest_frame.copy() if self.latest_frame is not None else None
                    cur_seq = self._frame_seq

                if display_frame is None:
                    blank = np.zeros((360, 640, 3), dtype=np.uint8)
                    cv2.putText(blank, "CAMERA OFFLINE / CONNECTING...", (120, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    ret, buffer = cv2.imencode('.jpg', blank, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    if ret:
                        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    await asyncio.sleep(0.3)
                    continue

                if draw_boxes:
                    from backend.core.state import get_highlighted_tids
                    active_alerts = get_highlighted_tids(self.camera_id)
                    for (x1, y1, x2, y2, conf, tid) in self.cached_boxes:
                        is_target = (tid == selected_tid and tid != -1) or (tid in active_alerts)
                        if is_target:
                            color = (0, 140, 255)
                            thickness = 3
                            label = f"#{tid} [VLM ALERT]"
                        else:
                            color = (0, 255, 0)
                            thickness = 2
                            label = f"#{tid}" if tid != -1 else ""
                        cv2.rectangle(display_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
                        text_str = f"WORKER {label}"
                        (text_w, text_h), _ = cv2.getTextSize(text_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                        cv2.rectangle(display_frame, (int(x1), int(y1) - text_h - 8), (int(x1) + text_w + 4, int(y1)), color, -1)
                        cv2.putText(display_frame, text_str, (int(x1) + 2, int(y1) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0) if is_target else (255, 255, 255), 1)

                ret, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ret:
                    last_seq = cur_seq
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        finally:
            self.stream_clients -= 1
            self.check_shutdown()

    def check_shutdown(self):
        if self.stream_clients <= 0 and not self.background_tracking:
            self.is_running = False
            with _engines_lock:
                if self.camera_id in _active_engines: del _active_engines[self.camera_id]
            
            # Reset metrics in shared state so counts immediately go to 0 in UI
            if hasattr(state, 'state_lock'):
                with state.state_lock:
                    if isinstance(state.shared_stats, dict) and "cameras" in state.shared_stats:
                        total_count = 0
                        total_alerts = 0
                        for cam in state.shared_stats["cameras"]:
                            if str(cam.get("id")) == self.camera_id:
                                cam["person_count"] = 0
                                cam["tracked_positions"] = []
                                cam["is_alert"] = False
                                cam["alert_type"] = None
                            total_count += cam.get("person_count", 0)
                            if cam.get("is_alert", False):
                                total_alerts += 1
                        state.shared_stats["person_count"] = total_count
                        state.shared_stats["active_alerts"] = total_alerts

# ─── RTSP Connections Core ─────────────────────────────────────────

def get_rtsp_url(camera_id):
    camera_id_str = str(camera_id)
    if camera_id_str.startswith("test_"):
        video_name = camera_id_str.replace("test_", "")
        # Resolve to test_video/<video_name>.mp4 relative to project root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        video_path = os.path.join(base_dir, "test_video", f"{video_name}.mp4")
        if os.path.exists(video_path):
            # Print removed to prevent console spam
            return video_path
        else:
            print(f"[STREAM ERROR] Test video file not found: {video_path}")
            return None
    return loader.get_physical_rtsp_url(camera_id)

def toggle_background_tracking(camera_id, enable=True):
    camera_id = str(camera_id)
    rtsp_url = get_rtsp_url(camera_id)
    with _engines_lock:
        if enable:
            if camera_id not in _active_engines:
                engine = StreamEngine(camera_id, rtsp_url, detect_people=False)
                engine.background_tracking = True
                engine.model = get_yolo_model(camera_id)
                engine.inference_started = True
                _active_engines[camera_id] = engine
                threading.Thread(target=engine._inference_loop, daemon=True).start()
            else:
                engine = _active_engines[camera_id]
                engine.background_tracking = True
                if not getattr(engine, 'inference_started', False):
                    engine.model = get_yolo_model(camera_id)
                    engine.inference_started = True
                    threading.Thread(target=engine._inference_loop, daemon=True).start()
        else:
            if camera_id in _active_engines:
                engine = _active_engines[camera_id]
                engine.background_tracking = False
                engine.check_shutdown()

def toggle_gate_counting(camera_id, enable=True):
    camera_id = str(camera_id)
    with _engines_lock:
        if camera_id in _active_engines:
            _active_engines[camera_id].gate_counting = enable
    if enable:
        active_gate_cameras.add(camera_id)
        toggle_background_tracking(camera_id, enable=True)
    else:
        active_gate_cameras.discard(camera_id)
        toggle_background_tracking(camera_id, enable=False)

def get_video_stream(camera_id, detect_people=False, selected_worker=''):
    camera_id = str(camera_id)
    rtsp_url = get_rtsp_url(camera_id)
    with _engines_lock:
        if camera_id not in _active_engines:
            engine = StreamEngine(camera_id, rtsp_url, detect_people)
            engine.inference_started = detect_people
            _active_engines[camera_id] = engine
            if detect_people:
                threading.Thread(target=engine._inference_loop, daemon=True).start()
        else:
            engine = _active_engines[camera_id]
            engine.detect_people = detect_people
            if detect_people:
                if engine.model is None:
                    engine.model = get_yolo_model(camera_id)
                if not getattr(engine, 'inference_started', False):
                    engine.inference_started = True
                    threading.Thread(target=engine._inference_loop, daemon=True).start()
            else:
                engine.check_shutdown()

    yield from engine.generate_frames(draw_boxes=detect_people, selected_worker=selected_worker)

async def get_video_stream_async(camera_id, detect_people=False, selected_worker=''):
    camera_id = str(camera_id)
    rtsp_url = get_rtsp_url(camera_id)
    with _engines_lock:
        if camera_id not in _active_engines:
            engine = StreamEngine(camera_id, rtsp_url, detect_people)
            engine.inference_started = detect_people
            _active_engines[camera_id] = engine
            if detect_people:
                threading.Thread(target=engine._inference_loop, daemon=True).start()
        else:
            engine = _active_engines[camera_id]
            engine.detect_people = detect_people
            if detect_people:
                if engine.model is None:
                    engine.model = get_yolo_model(camera_id)
                if not getattr(engine, 'inference_started', False):
                    engine.inference_started = True
                    threading.Thread(target=engine._inference_loop, daemon=True).start()
            else:
                engine.check_shutdown()

    async for frame in engine.generate_frames_async(draw_boxes=detect_people, selected_worker=selected_worker):
        yield frame

def process_video_click(camera_id, x_norm, y_norm):
    camera_id = str(camera_id)
    with _engines_lock:
        if camera_id in _active_engines:
            tid = _active_engines[camera_id].get_worker_from_click(x_norm, y_norm)
            if tid != -1:
                return f"{camera_id}-{tid}"
    return -1
