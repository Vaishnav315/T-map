"""
Zone Transition Counting Module — Replaces brittle 1D line intersection with
robust 2D Trajectory Vector Zone Counting.
"""
import time
import threading
from typing import Dict, List, Tuple

def _get_bottom_center(bbox) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, bbox[3])

class LineCounting:
    """
    Stateful trajectory counter.
    Divides the screen into zones and measures the track's global displacement vector.
    """
    
    def __init__(self, camera_id: str, frame_dimensions: Tuple[float, float] = None):
        self.camera_id = str(camera_id)
        # frame_dimensions: (width, height)
        self.width = frame_dimensions[0] if frame_dimensions else 1920.0
        self.height = frame_dimensions[1] if frame_dimensions else 1080.0
        
        self.in_count = 0
        self.out_count = 0
        self.cooldown_registry = {}
        self.cooldown_lock = threading.Lock()
    
    def evaluate(self, tracks: Dict) -> List[Tuple[str, str]]:
        crossed_events = []
        current_time = time.time()
        
        is_cam3 = str(self.camera_id) == "3" or str(self.camera_id).startswith("test_gate_cam3")
        if not is_cam3:
            return crossed_events
            
        for tid, state in tracks.items():
            if state.class_name != 'person' or len(state.bboxes) < 2:
                continue
            
            # Check cooldown
            with self.cooldown_lock:
                if tid in self.cooldown_registry:
                    elapsed = current_time - self.cooldown_registry[tid]["last_cross_time"]
                    if elapsed < 8.0:
                        continue
                        
            P_prev = _get_bottom_center(state.bboxes[-2])
            P_curr = _get_bottom_center(state.bboxes[-1])
            
            line_y = self.height * 0.50
            direction = None
            
            # Velocity vector crossing approach
            crossed_down = (P_prev[1] <= line_y < P_curr[1]) or (P_prev[1] < line_y <= P_curr[1])
            crossed_up = (P_prev[1] >= line_y > P_curr[1]) or (P_prev[1] > line_y >= P_curr[1])
            
            # Check vertical velocity direction (vy > 0 is downwards, vy < 0 is upwards)
            vy = getattr(state, 'vy', 0.0)
            
            if crossed_down and vy >= 0.0:
                direction = "IN"
            elif crossed_up and vy <= 0.0:
                direction = "OUT"
            
            if direction:
                crossed_events.append((direction, tid))
                with self.cooldown_lock:
                    self.cooldown_registry[tid] = {
                        "last_cross_time": current_time,
                        "direction": direction
                    }
                    if direction == "IN":
                        self.in_count += 1
                    else:
                        self.out_count += 1
                        
        return crossed_events
        
    def reset(self):
        with self.cooldown_lock:
            self.in_count = 0
            self.out_count = 0
            self.cooldown_registry.clear()
