"""
Idle Monitoring — WARNING severity.

Trigger: Person(s) with minimal cumulative displacement over a 5-minute window.
Not velocity=0 (unrealistic), but total distance traveled < threshold over time.
"""
import time
import math
from typing import Dict, List, Tuple


# Thresholds
IDLE_WINDOW_SEC = 300.0              # 5 minute observation window
IDLE_MAX_DISPLACEMENT_PX = 50.0     # If person moved less than 50px total in 5min = idle
MIN_HISTORY_FRAMES = 10              # Need at least 10 frames of history


def _get_bottom_center(bbox) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, bbox[3])


def detect_idle(tracks: Dict, camera_id: str) -> List[dict]:
    """
    Detects people who have barely moved over a 5-minute window.
    Uses cumulative displacement (total distance traveled), not instantaneous velocity.
    """
    alerts = []
    now = time.time()
    
    for tid, state in tracks.items():
        if state.class_name != 'person':
            continue
        
        if len(state.bboxes) < MIN_HISTORY_FRAMES:
            continue
        
        # Check if we have enough time history
        track_duration = now - state.start_time if state.start_time else 0
        if track_duration < IDLE_WINDOW_SEC:
            continue
        
        # Calculate cumulative displacement over the window
        total_displacement = 0.0
        for i in range(1, len(state.bboxes)):
            p1 = _get_bottom_center(state.bboxes[i - 1])
            p2 = _get_bottom_center(state.bboxes[i])
            total_displacement += math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        
        if total_displacement < IDLE_MAX_DISPLACEMENT_PX:
            alerts.append({
                "event_type": "IDLE_DETECTED",
                "severity": "WARNING",
                "camera_id": camera_id,
                "track_id": tid,
                "bbox": state.bboxes[-1],
                "description": f"Person #{tid} idle for {track_duration/60:.1f}min (moved {total_displacement:.0f}px total).",
                "vlm_prompt": "Is this person idle or sleeping, or are they doing seated/stationary work at their station? Answer briefly."
            })
    
    return alerts
