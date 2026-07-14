"""
Slip/Trip Hazard Detection — WARNING severity.

Runs a periodic full-frame VLM scan every 90 seconds to detect
wet floors, spills, or trip hazards. The alert is NOT fired immediately —
it is only logged when the VLM confirms an actual hazard is present.

No evidence screenshot is generated (WARNING severity — policy: only HIGH/CRITICAL).
"""
import time
from typing import List
import numpy as np

_last_scan_times = {}

# How often to scan each camera (seconds)
SCAN_INTERVAL_SEC = 90.0


def detect_slip_hazard(camera_id: str, raw_frame: np.ndarray) -> List[dict]:
    """
    Periodically queues a full-frame VLM hazard scan.
    Only produces an alert if the VLM confirms a genuine hazard — 
    handled inside vlm_integration.py via the VLM prompt answer.
    """
    alerts = []
    now = time.time()

    last_scan = _last_scan_times.get(camera_id, 0)

    # Run once every SCAN_INTERVAL_SEC per camera
    if (now - last_scan) < SCAN_INTERVAL_SEC:
        return alerts

    _last_scan_times[camera_id] = now

    # We still emit the alert dict so the VLM cascade runs, but:
    #   - severity = "WARNING" → no screenshot will be saved (policy gate)
    #   - description is minimal — only written to DB if VLM confirms hazard
    alerts.append({
        "event_type": "SLIP_TRIP_HAZARD",
        "severity": "WARNING",
        "camera_id": camera_id,
        "track_id": None,
        "bbox": None,
        "description": "Periodic floor safety scan triggered.",
        "vlm_prompt": (
            "You are a safety inspector reviewing a factory/workplace floor camera. "
            "Look carefully at the floor and ground level only. "
            "Are there any wet floors, liquid spills, exposed cables, loose materials, "
            "or objects that pose a trip or slip hazard? "
            "If YES: describe the hazard in one sentence. "
            "If NO hazard is visible: respond with exactly 'NO HAZARD'."
        )
    })

    return alerts
