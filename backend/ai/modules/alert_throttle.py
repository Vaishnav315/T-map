"""
Alert Throttle — Centralized cooldown + evidence capture.

Prevents duplicate alerts for the same (event_type, camera_id, track_id)
within a configurable cooldown window.

Evidence Policy:
  - Only HIGH and CRITICAL alerts get a screenshot saved.
  - WARNING alerts: NO screenshot (reduces folder flooding).
  - LOW / INFO alerts: NO screenshot.
  - Hard global cap: max 30 evidence images per hour across all cameras.
    After cap is reached, no more screenshots are saved until the hour rolls over.

Severity Tier Reference (used system-wide):
  CRITICAL  — Life safety / medical emergency / major security breach
  HIGH      — Significant risk, zone intrusion, unattended objects
  WARNING   — Operational concern, crowd gathering, idling workforce
  LOW       — Informational notice, gate events, normal VLM descriptions
"""
import time
import os
import threading
import cv2
import numpy as np

_throttle_cache = {}  # key -> {"last_fired": timestamp, "persist_start": timestamp}
_throttle_lock = threading.Lock()

# Evidence storage directory
EVIDENCE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "evidence"))
os.makedirs(EVIDENCE_DIR, exist_ok=True)

# ── Evidence Rate Limiter ────────────────────────────────────────────
# Severities that are allowed to save evidence screenshots
EVIDENCE_ALLOWED_SEVERITIES = {"CRITICAL", "HIGH"}

# Global cap: max screenshots per rolling hour window
EVIDENCE_HOURLY_CAP = 30
_evidence_timestamps = []   # timestamps of screenshots saved this hour
_evidence_lock = threading.Lock()


def _can_save_evidence(severity: str) -> bool:
    """
    Returns True only if:
      1. Severity is HIGH or CRITICAL
      2. Global hourly cap has not been reached
    """
    if severity.upper() not in EVIDENCE_ALLOWED_SEVERITIES:
        return False
    now = time.time()
    with _evidence_lock:
        # Prune timestamps older than 1 hour
        cutoff = now - 3600.0
        while _evidence_timestamps and _evidence_timestamps[0] < cutoff:
            _evidence_timestamps.pop(0)
        if len(_evidence_timestamps) >= EVIDENCE_HOURLY_CAP:
            print(f"[EVIDENCE] Hourly cap ({EVIDENCE_HOURLY_CAP}) reached — skipping screenshot.")
            return False
        _evidence_timestamps.append(now)
        return True


# ── Severity-Tiered Cooldowns ────────────────────────────────────────
# These are the minimum seconds between re-firing the SAME alert type
# for the SAME (event_type, camera_id, track_id) combination.
SEVERITY_COOLDOWNS = {
    "CRITICAL": 120.0,   # 2 minutes between repeat CRITICAL alerts
    "HIGH":      90.0,   # 90 seconds between HIGH alerts
    "WARNING":  180.0,   # 3 minutes between WARNING alerts
    "LOW":      300.0,   # 5 minutes between LOW / INFO alerts
    "INFO":     300.0,   # same as LOW
}

DEFAULT_COOLDOWN = 120.0


def _make_key(event_type: str, camera_id: str, track_id) -> str:
    return f"{event_type}_{camera_id}_{track_id}"


def is_throttled(event_type: str, camera_id: str, track_id, cooldown_sec: float = None) -> bool:
    """Returns True if this event was already fired within the cooldown window.
    If cooldown_sec is None, uses DEFAULT_COOLDOWN."""
    key = _make_key(event_type, camera_id, track_id)
    now = time.time()
    cd = cooldown_sec if cooldown_sec is not None else DEFAULT_COOLDOWN
    with _throttle_lock:
        entry = _throttle_cache.get(key)
        if entry and (now - entry["last_fired"]) < cd:
            return True
        return False


def record_fired(event_type: str, camera_id: str, track_id):
    """Marks this event as fired right now."""
    key = _make_key(event_type, camera_id, track_id)
    now = time.time()
    with _throttle_lock:
        if key not in _throttle_cache:
            _throttle_cache[key] = {"last_fired": now, "persist_start": now}
        else:
            _throttle_cache[key]["last_fired"] = now


def get_cooldown_for_severity(severity: str) -> float:
    """Returns the appropriate cooldown in seconds for the given severity tier."""
    return SEVERITY_COOLDOWNS.get(severity.upper(), DEFAULT_COOLDOWN)


def get_persist_duration(event_type: str, camera_id: str, track_id) -> float:
    """Returns how long (seconds) this alert has been persisting."""
    key = _make_key(event_type, camera_id, track_id)
    with _throttle_lock:
        entry = _throttle_cache.get(key)
        if entry:
            return time.time() - entry["persist_start"]
    return 0.0


def cleanup_stale(max_age: float = 300.0):
    """Garbage collect throttle entries older than max_age seconds."""
    now = time.time()
    with _throttle_lock:
        stale = [k for k, v in _throttle_cache.items() if (now - v["last_fired"]) > max_age]
        for k in stale:
            del _throttle_cache[k]


def _cleanup_evidence_directory():
    """Keeps the evidence directory clean by retaining only the 20 most recent files."""
    try:
        if not os.path.exists(EVIDENCE_DIR):
            return
        files = [os.path.join(EVIDENCE_DIR, f) for f in os.listdir(EVIDENCE_DIR) 
                 if os.path.isfile(os.path.join(EVIDENCE_DIR, f)) and f.endswith(".jpg")]
        # Sort by modification time (oldest first)
        files.sort(key=os.path.getmtime)
        max_files = 20
        if len(files) > max_files:
            num_to_delete = len(files) - max_files
            for i in range(num_to_delete):
                try:
                    os.remove(files[i])
                    print(f"[EVIDENCE CLEANUP] Deleted oldest file: {os.path.basename(files[i])}")
                except Exception as ex:
                    print(f"[EVIDENCE CLEANUP ERROR] Failed to delete {files[i]}: {ex}")
    except Exception as e:
        print(f"[EVIDENCE CLEANUP ERROR] Failed: {e}")

def save_evidence_screenshot(camera_id: str, event_type: str, track_id, frame: np.ndarray,
                              bbox=None, severity: str = "CRITICAL") -> str:
    """
    Saves an evidence image for the alert, subject to the evidence policy:
      - Only HIGH / CRITICAL alerts get a screenshot.
      - Global hourly cap enforced.

    If bbox is provided, saves a padded crop around the target.
    If bbox is None (full-scene events like ST-GLAD), saves the full frame resized.
    Returns the filename, or "" if evidence was skipped.
    """
    if not _can_save_evidence(severity):
        return ""

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    tid_str = str(track_id) if track_id is not None else "scene"
    filename = f"{camera_id}_{event_type}_{tid_str}_{timestamp_str}.jpg"
    filepath = os.path.join(EVIDENCE_DIR, filename)

    try:
        if bbox is not None and len(bbox) == 4:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = map(int, bbox)
            # 30% padding around the target
            bw, bh = x2 - x1, y2 - y1
            pad_x, pad_y = int(bw * 0.3), int(bh * 0.3)
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(w, x2 + pad_x)
            cy2 = min(h, y2 + pad_y)
            crop = frame[cy1:cy2, cx1:cx2]
            if crop.size > 0:
                cv2.imwrite(filepath, crop, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            else:
                cv2.imwrite(filepath, cv2.resize(frame, (640, 360)), [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        else:
            # Full frame evidence (resized for storage efficiency)
            cv2.imwrite(filepath, cv2.resize(frame, (640, 360)), [int(cv2.IMWRITE_JPEG_QUALITY), 65])

        print(f"[EVIDENCE] Saved: {filename} (severity={severity})")
        # Run directory cleanup
        _cleanup_evidence_directory()
        return filename
    except Exception as e:
        print(f"[EVIDENCE] Failed to save screenshot: {e}")
        return ""
