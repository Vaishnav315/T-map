"""
Crowd Anomaly / Gathering Detection — WARNING severity.

Trigger: 3+ people clustered within proximity, low cumulative movement for >3min.
These are people standing around chatting/doing nothing — not actively working.
"""
import time
import math
import numpy as np
from typing import Dict, List, Tuple


# Thresholds
CLUSTER_DISTANCE_PX = 100.0        # Pixel distance to consider "clustered" (raw frame coords)
MIN_GROUP_SIZE = 3                   # Minimum people to form a "gathering"
LOW_MOVEMENT_THRESHOLD = 2.0        # Velocity below this = "barely moving"
GATHERING_TIME_SEC = 180.0          # 3 minutes of sustained gathering before alert


def _get_bottom_center(bbox) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, bbox[3])


def detect_crowd_anomaly(tracks: Dict, camera_id: str, gathering_timers: Dict) -> List[dict]:
    """
    Detects groups of 3+ people standing around with minimal movement.
    
    gathering_timers: Dict[frozenset_of_tids -> start_time] — maintained by caller (EventManager).
    Returns list of alert event dicts.
    """
    alerts = []
    
    # Get all person tracks with enough history
    persons = [(tid, state) for tid, state in tracks.items() 
               if state.class_name == 'person' and len(state.bboxes) > 0]
    
    if len(persons) < MIN_GROUP_SIZE:
        gathering_timers.clear()
        return alerts
    
    # Extract positions and velocities
    positions = []
    velocities = []
    tids = []
    bboxes = []
    
    for tid, state in persons:
        positions.append(_get_bottom_center(state.bboxes[-1]))
        velocities.append(state.velocity)
        tids.append(tid)
        bboxes.append(state.bboxes[-1])
    
    positions = np.array(positions)
    velocities = np.array(velocities)
    
    # Find slow-moving people (low cumulative movement)
    slow_mask = velocities < LOW_MOVEMENT_THRESHOLD
    slow_indices = np.where(slow_mask)[0]
    
    if len(slow_indices) < MIN_GROUP_SIZE:
        gathering_timers.clear()
        return alerts
    
    # Compute pairwise distances between slow people
    slow_positions = positions[slow_indices]
    diff = slow_positions[:, np.newaxis, :] - slow_positions[np.newaxis, :, :]
    dists = np.sqrt(np.sum(diff**2, axis=-1))
    
    # Find clusters: people within CLUSTER_DISTANCE_PX of each other
    close_pairs = dists < CLUSTER_DISTANCE_PX
    np.fill_diagonal(close_pairs, False)
    
    # Build a simple cluster via connected components
    clustered = set()
    for i in range(len(slow_indices)):
        neighbors = np.where(close_pairs[i])[0]
        if len(neighbors) >= (MIN_GROUP_SIZE - 1):
            clustered.add(slow_indices[i])
            for n in neighbors:
                clustered.add(slow_indices[n])
    
    if len(clustered) >= MIN_GROUP_SIZE:
        cluster_key = frozenset(tids[i] for i in clustered)
        now = time.time()
        
        if cluster_key not in gathering_timers:
            gathering_timers[cluster_key] = now
        
        elapsed = now - gathering_timers[cluster_key]
        
        if elapsed >= GATHERING_TIME_SEC:
            # Pick a representative bbox (center of the cluster)
            cluster_bboxes = [bboxes[i] for i in clustered]
            # Use the first person's bbox for evidence cropping
            rep_bbox = cluster_bboxes[0]
            rep_tid = tids[list(clustered)[0]]
            
            alerts.append({
                "event_type": "CROWD_GATHERING",
                "severity": "WARNING",
                "camera_id": camera_id,
                "track_id": rep_tid,
                "bbox": rep_bbox,
                "description": f"{len(clustered)} people gathered idle for {elapsed/60:.1f}min.",
                "vlm_prompt": "Are these people working together on a task, or standing idle without any productive activity? Answer briefly."
            })
    else:
        gathering_timers.clear()
    
    return alerts
