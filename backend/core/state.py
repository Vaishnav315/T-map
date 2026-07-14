import threading
import queue
import time
import json
from backend.core import database
from backend.ai.tracker import WorkerTracker

# --- Clean Global State Structures ---

# These dictionaries will hold live frame data and inference results updated by your cameras
shared_stats = {
    "person_count": 0,
    "active_alerts": 0,
    "trail_duration": 60,
    "global_gate_in": 0,
    "global_gate_out": 0,
    "cameras": []
}

active_ai_modules = {} # camera_id -> list of module_ids
worker_states = {} # camera_id -> {tid: {'state': 'MOVING', 'centroid': (cx, cy), 'stationary_since': timestamp}}
alert_highlights = {} # camera_id -> {tid: expiration_timestamp}
state_lock = threading.Lock()

global_tracker = WorkerTracker(ghost_timeout=8.0, alpha=0.30)
last_system_log_time = 0

# ── SSE Alert Streaming ──────────────────────────────────────────
# Subscribers: list of queue.Queue objects, one per connected SSE client
_sse_subscribers = []
_sse_lock = threading.Lock()
_unread_alert_count = 0


def subscribe_alerts() -> queue.Queue:
    """Register a new SSE client. Returns a queue to listen on."""
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_subscribers.append(q)
    return q


def unsubscribe_alerts(q: queue.Queue):
    """Remove an SSE client queue."""
    with _sse_lock:
        if q in _sse_subscribers:
            _sse_subscribers.remove(q)


def _broadcast_alert(alert_entry: dict):
    """Push alert to all connected SSE clients (non-blocking)."""
    with _sse_lock:
        dead = []
        for q in _sse_subscribers:
            try:
                q.put_nowait(alert_entry)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_subscribers.remove(q)


def get_unread_count() -> int:
    with state_lock:
        return _unread_alert_count


def reset_unread_count():
    global _unread_alert_count
    with state_lock:
        _unread_alert_count = 0


# ── Core State Functions ──────────────────────────────────────────

def init_state():
    pass

def trigger_highlight(camera_id, tid, duration_secs=5.0):
    with state_lock:
        if camera_id not in alert_highlights:
            alert_highlights[camera_id] = {}
        alert_highlights[camera_id][tid] = time.time() + duration_secs

def get_highlighted_tids(camera_id):
    with state_lock:
        if camera_id not in alert_highlights:
            return set()
        
        now = time.time()
        active = set()
        to_delete = []
        for tid, expiry in alert_highlights[camera_id].items():
            if now < expiry:
                active.add(tid)
            else:
                to_delete.append(tid)
                
        for tid in to_delete:
            del alert_highlights[camera_id][tid]
            
        return active

def get_worker_state(camera_id, tid):
    with state_lock:
        if camera_id not in worker_states:
            worker_states[camera_id] = {}
        if tid not in worker_states[camera_id]:
            worker_states[camera_id][tid] = {'state': 'MOVING', 'centroid': None, 'stationary_since': None}
        return worker_states[camera_id][tid]

def set_worker_state(camera_id, tid, data_dict):
    with state_lock:
        if camera_id not in worker_states:
            worker_states[camera_id] = {}
        if tid not in worker_states[camera_id]:
            worker_states[camera_id][tid] = {}
        worker_states[camera_id][tid].update(data_dict)


def set_ai_modules(camera_id, modules_list):
    with state_lock:
        active_ai_modules[camera_id] = modules_list

def clear_ai_module(camera_id):
    with state_lock:
        if camera_id in active_ai_modules:
            del active_ai_modules[camera_id]

def get_ai_modules(camera_id):
    with state_lock:
        return active_ai_modules.get(camera_id, [])

def initialize_state(camera_registry):
    """Sets up empty tracking slots for each camera on server start."""
    global shared_stats
    with state_lock:
        shared_stats["cameras"] = [
            {
                "id": cam_id,
                "name": meta.get("Name", f"Cam {cam_id}"),
                "status": "Active",
                "person_count": 0,
                "is_alert": False,
                "alert_type": None,
                "rtsp_active": True
            }
            for cam_id, meta in camera_registry.items()
        ]

def add_real_log(camera_id, camera_name, event_type, severity, details):
    """Thread-safe function for general/system events."""
    database.insert_system_log(camera_id, camera_name, event_type, severity, details)

def add_vlm_log(camera_id, camera_name, severity, details):
    """Thread-safe function for routine VLM inference descriptions."""
    database.insert_vlm_log(camera_id, camera_name, severity, details)

def add_alert_log(camera_id, camera_name, event_type, severity, details, evidence_file="", vlm_status="PENDING"):
    """Thread-safe function for Actionable AI Alerts with evidence."""
    global _unread_alert_count
    
    log_entry = database.insert_alert_log(camera_id, camera_name, event_type, severity, details, evidence_file, vlm_status)
    
    with state_lock:
        _unread_alert_count += 1
    
    # Broadcast to SSE clients
    _broadcast_alert(log_entry)
    return log_entry

def update_alert_log_vlm(alert_id, vlm_status, vlm_description):
    """Updates an existing alert with VLM verification results and broadcasts the update."""
    updated_entry = database.update_alert_vlm(alert_id, vlm_status, vlm_description)
    if updated_entry:
        updated_entry["is_update"] = True
        _broadcast_alert(updated_entry)
        return updated_entry
    return None


def update_camera_metrics(camera_id, person_count, is_alert=False, alert_type=None, people_in_count=None, people_out_count=None):
    """
    Call this function from your ML loop to pass live predictions directly to the web dashboard.
    """
    global shared_stats
    with state_lock:
        total_count = 0
        total_alerts = 0
        
        for cam in shared_stats["cameras"]:
            if cam["id"] == camera_id:
                cam["person_count"] = person_count
                cam["is_alert"] = is_alert
                cam["alert_type"] = alert_type
                if people_in_count is not None:
                    cam["gate_in"] = people_in_count
                if people_out_count is not None:
                    cam["gate_out"] = people_out_count
            
            total_count += cam.get("person_count", 0)
            if cam.get("is_alert", False):
                total_alerts += 1
                
        shared_stats["person_count"] = total_count
        shared_stats["active_alerts"] = total_alerts

def start_state_updater():
    """Starts background updater thread and VLM worker."""
    def _updater():
        while True:
            time.sleep(5)
            # Background housekeeping can go here if needed.
    
    # Start housekeeping thread
    t = threading.Thread(target=_updater, daemon=True)
    t.start()
    
    # Start VLM processing queue
    try:
        from backend.ai.vlm_integration import start_vlm_worker
        start_vlm_worker()
        print("[STATE] Background state updater and VLM queue started.")
    except Exception as e:
        print(f"[STATE] Error starting VLM worker: {e}")
