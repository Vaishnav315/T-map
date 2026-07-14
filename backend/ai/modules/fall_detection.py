"""
Fall Detection Module — CRITICAL severity, instant alert.

Trigger: Sudden bbox aspect ratio flip (tall→wide) + rapid velocity drop.
A standing person (h > w) suddenly becomes lying (w > h) = fall.
"""
import time
from typing import Dict, List

# Thresholds
FALL_ASPECT_RATIO_THRESHOLD = 1.25   # w/h > 1.25 means person is wider than tall (lying down)
FALL_VELOCITY_DROP_THRESHOLD = 0.5   # Velocity must drop to near-zero after fall
FALL_CONFIRMATION_SEC = 3.0          # Must persist for 3s to confirm (not just bending down)


def detect_falls(tracks: Dict, camera_id: str) -> List[dict]:
    """
    Checks all person tracks for fall indicators using a dual-trigger algorithm:
    1. Aspect Ratio: w/h > 0.95 (person is lying flat).
    2. Height Collapse: Current height is < 55% of their maximum standing height.
    Requires the track to be stationary (velocity < 1.5) and confirmed for 2.0 seconds.
    """
    alerts = []
    
    for tid, state in tracks.items():
        if state.class_name != 'person' or len(state.bboxes) < 2:
            continue
            
        bbox = state.bboxes[-1]
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        
        if h <= 0:
            continue
            
        aspect = w / h
        
        # Dynamic calibration: Track maximum height when aspect ratio is thin/standing
        if aspect < 0.65:
            if not hasattr(state, 'max_standing_height') or h > state.max_standing_height:
                state.max_standing_height = h
        
        # Fall conditions
        is_lying = aspect > 0.95  # Lying flat
        
        # Relative height drop check (sudden collapse)
        has_collapsed = False
        height_pct = 1.0
        if hasattr(state, 'max_standing_height') and state.max_standing_height > 0:
            height_pct = h / state.max_standing_height
            if height_pct < 0.55:  # Height dropped by >45%
                has_collapsed = True
                
        # Stationary check: account for bounding box jitter in pixel space (typically 10-35 px/s)
        is_stationary = state.velocity < 35.0
        
        # Stationary check: account for bounding box jitter in pixel space (typically 10-35 px/s)
        is_stationary = state.velocity < 35.0
        
        elapsed = 0.0
        if (is_lying or has_collapsed) and is_stationary:
            if state.anomaly_start_time == 0.0:
                state.anomaly_start_time = state.timestamps[-1]
            elapsed = state.timestamps[-1] - state.anomaly_start_time
        else:
            state.anomaly_start_time = 0.0
            
        # Debug logging to see exactly why it is or isn't triggering in the console
        # print(f"[FALL DEBUG] Person #{tid} | Aspect: {aspect:.2f} | Height Pct: {height_pct:.2f} (H:{h:.1f}/MaxH:{getattr(state, 'max_standing_height', 0.0):.1f}) | Velocity: {state.velocity:.1f} | Lying: {is_lying} | Collapsed: {has_collapsed} | Stationary: {is_stationary} | Elapsed: {elapsed:.1f}s")
        
        if (is_lying or has_collapsed) and is_stationary and elapsed >= 2.0:
            trigger_reason = "lying flat" if is_lying else f"sudden height collapse ({int((1 - h / state.max_standing_height) * 100)}% height drop)"
            alerts.append({
                "event_type": "FALL_DETECTED",
                "severity": "CRITICAL",
                "camera_id": camera_id,
                "track_id": tid,
                "bbox": bbox,
                "description": f"Person #{tid} collapsed — {trigger_reason} for {elapsed:.1f}s with no movement.",
                "vlm_prompt": "Is this person lying on the ground due to a fall, collapse, or medical emergency? Answer YES or NO."
            })
            
    return alerts
