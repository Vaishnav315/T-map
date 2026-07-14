import time
from typing import Dict, List

# Tracking consecutive frames where climbing behavior is sustained per track
_climb_counters: Dict[str, int] = {}
_last_alert_times: Dict[str, float] = {}

CLIMB_SUSTAIN_REQUIRED = 2     # Lowered for arbitrary test video
V_Y_THRESHOLD = -2.0          # Any upward movement
ASPECT_RATIO_SPIKE = 0.7       # Any squatting/crouching

def detect_wall_climb(tracks: Dict, camera_id: str, wall_y_bounds: tuple) -> List[dict]:
    """
    Perimeter Wall Climbing Detection Engine.
    Runs in parallel with ST-GLAD to handle solitary (n=1) intruders.
    
    wall_y_bounds: (y_top, y_bottom) pixel coordinates defining where the wall is in the frame.
    """
    global _climb_counters
    alerts = []
    
    y_top, y_bottom = wall_y_bounds

    for tid, state in tracks.items():
        if 'bboxes' not in state or len(state['bboxes']) < 5:
            continue

        bbox = state['bboxes'][-1]
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        cy = (y1 + y2) / 2  # Bounding box center Y
        
        # 1. Spatial Filter: Is the person physically overlapping with the wall zone?
        if not (y_top <= y2 <= y_bottom):
            _climb_counters[f"{camera_id}_{tid}"] = 0
            continue
            
        # 2. Temporal Filter: Extract vertical velocity (vy) from track state
        # In screen coordinates, moving UP means Y decreases (negative velocity)
        # Note: If ByteTrack state doesn't have .vy directly, we compute it from last 5 frames.
        if 'vy' in state:
            vy = state['vy']
        else:
            prev_y = state['bboxes'][-5][3]
            vy = (y2 - prev_y) / 5.0
        
        # 3. Morphological Filter: Calculate current aspect ratio
        aspect_ratio = w / float(h) if h > 0 else 0

        # Check conditions: Continuous upward movement OR body compression atop the wall
        is_climbing = (vy < V_Y_THRESHOLD) or (y2 < (y_top + 50) and aspect_ratio > ASPECT_RATIO_SPIKE)

        track_key = f"{camera_id}_{tid}"

        if is_climbing:
            _climb_counters[track_key] = _climb_counters.get(track_key, 0) + 1
        else:
            _climb_counters[track_key] = 0
            continue

        # 4. Trigger alert if sustained
        if _climb_counters[track_key] >= CLIMB_SUSTAIN_REQUIRED:
            now = time.time()
            if now - _last_alert_times.get(camera_id, 0) > 15.0:
                alerts.append({
                    "type": "PERIMETER_CLIMB",
                    "camera_id": camera_id,
                    "track_id": tid,
                    "bbox": bbox,
                    "vlm_use_full_frame": True, 
                    "severity": "CRITICAL",
                    "details": f"Potential intruder scaling perimeter wall. Track {tid} vertical velocity: {vy:.1f}px/f.",
                    "vlm_prompt": (
                        "You are a security AI. A spatial algorithm flags a vertical motion anomaly climbing the perimeter wall. "
                        "Look closely at the wall area. Is someone attempting to scale, jump over, or sit atop the fence/wall? "
                        "Reply YES or NO first, then write a one-sentence descriptive warning."
                    )
                })
                _last_alert_times[camera_id] = now
            # Reset counter to enforce cooldown
            _climb_counters[track_key] = 0

    return alerts
