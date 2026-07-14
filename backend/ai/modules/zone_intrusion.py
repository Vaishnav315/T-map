"""
Zone Intrusion Detection — HIGH severity.

Trigger: Person centroid enters a restricted polygon for >3 consecutive frames.
Zones are configurable per camera.
"""
import time
from typing import Dict, List, Tuple


# Default restricted zones per camera (raw frame pixel coordinates)
# Override these via camera_registry.json or config
DEFAULT_ZONES = {}  # camera_id -> list of polygons. Empty = no zones configured.


def _point_in_polygon(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    """Ray-casting algorithm for point-in-polygon test."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]
        if min(p1y, p2y) < y <= max(p1y, p2y):
            if x <= max(p1x, p2x):
                if p1y != p2y:
                    xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if p1x == p2x or x <= xinters:
                    inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _get_centroid(bbox) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


# Per-camera intrusion frame counters: camera_id -> {track_id -> consecutive_frames_in_zone}
_intrusion_counters = {}

REQUIRED_CONSECUTIVE_FRAMES = 3


def detect_zone_intrusion(tracks: Dict, camera_id: str, zones: List[List[Tuple[float, float]]] = None) -> List[dict]:
    """
    Checks if any person has been inside a restricted zone for consecutive frames.
    
    zones: List of polygons [(x1,y1), (x2,y2), ...] in raw frame coordinates.
           If None, uses DEFAULT_ZONES for this camera.
    """
    alerts = []
    
    if zones is None:
        zones = DEFAULT_ZONES.get(camera_id, [])
    
    if not zones:
        return alerts  # No zones configured for this camera
    
    if camera_id not in _intrusion_counters:
        _intrusion_counters[camera_id] = {}
    
    counters = _intrusion_counters[camera_id]
    active_tids = set()
    
    for tid, state in tracks.items():
        if state.class_name != 'person' or len(state.bboxes) < 1:
            continue
        
        active_tids.add(tid)
        cx, cy = _get_centroid(state.bboxes[-1])
        
        in_zone = False
        for polygon in zones:
            if _point_in_polygon(cx, cy, polygon):
                in_zone = True
                break
        
        if in_zone:
            counters[tid] = counters.get(tid, 0) + 1
            
            if counters[tid] >= REQUIRED_CONSECUTIVE_FRAMES:
                alerts.append({
                    "event_type": "ZONE_INTRUSION",
                    "severity": "HIGH",
                    "camera_id": camera_id,
                    "track_id": tid,
                    "bbox": state.bboxes[-1],
                    "description": f"Person #{tid} entered restricted zone.",
                    "vlm_prompt": "Is this person in a restricted or hazardous area where they should not be? Answer briefly."
                })
        else:
            counters[tid] = 0
    
    # Cleanup counters for tracks that left
    stale = [tid for tid in counters if tid not in active_tids]
    for tid in stale:
        del counters[tid]
    
    return alerts
