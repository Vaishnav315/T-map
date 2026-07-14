"""
Event Manager — Thin orchestrator for AI safety modules.

Delegates all detection logic to backend.ai.modules.*.
Manages TrackState, calls each enabled module, and routes 
alerts through the throttle → VLM cascade pipeline.
"""
import time
import math
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import numpy as np

from backend.ai.modules.fall_detection import detect_falls
from backend.ai.modules.crowd_anomaly import detect_crowd_anomaly
from backend.ai.modules.idle_monitoring import detect_idle
from backend.ai.modules.zone_intrusion import detect_zone_intrusion
from backend.ai.modules.line_counting import LineCounting
# from backend.ai.modules.unattended_object import detect_unattended_object
from backend.ai.modules.slip_hazard import detect_slip_hazard
from backend.ai.modules import alert_throttle


# ═══════════════════════════════════════════════════════════════
#  Track State — shared data structure for all modules
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrackState:
    track_id: str
    class_name: str
    bboxes: List[List[float]] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    last_updated: float = 0.0
    
    velocity: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    anomaly_start_time: float = 0.0 
    
    counted: bool = False
    start_point: Tuple[float, float] = None
    start_time: float = 0.0
    
    def update(self, bbox: List[float], timestamp: float):
        self.bboxes.append(bbox)
        self.timestamps.append(timestamp)
        self.last_updated = timestamp
        
        if self.start_point is None:
            self.start_point = get_bottom_center(bbox)
            self.start_time = timestamp
            
        if len(self.bboxes) > 60: 
            self.bboxes.pop(0)
            self.timestamps.pop(0)
            
        self._calculate_velocity()
            
    def _calculate_velocity(self):
        if len(self.bboxes) < 2:
            self.velocity = 0.0
            self.vx = 0.0
            self.vy = 0.0
            return
            
        t1, t2 = self.timestamps[-2], self.timestamps[-1]
        dt = t2 - t1
        if dt <= 0: return
            
        b1, b2 = self.bboxes[-2], self.bboxes[-1]
        cx1, cy1 = (b1[0] + b1[2])/2, b1[3]
        cx2, cy2 = (b2[0] + b2[2])/2, b2[3]
        
        dx = cx2 - cx1
        dy = cy2 - cy1
        dist = math.hypot(dx, dy)
        self.velocity = dist / dt
        self.vx = dx / dt
        self.vy = dy / dt


def get_bottom_center(bbox: List[float]) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, bbox[3])


# ═══════════════════════════════════════════════════════════════
#  Event Manager — Orchestrator
# ═══════════════════════════════════════════════════════════════

class EventManager:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.tracks: Dict[str, TrackState] = {}
        
        # Per-module state
        self.gathering_timers: Dict = {}
        
        # Zone Counting state
        self.ENABLE_LINE_COUNTING = False
        self.in_count = 0
        self.out_count = 0
        
        self.line_counter = LineCounting(self.camera_id, frame_dimensions=None)
        
        # Throttle cleanup interval
        self._last_cleanup = time.time()

    def update(self, frame_data: List[dict], raw_frame: np.ndarray):
        """
        Main entry point called every inference frame.
        Updates tracks, runs modules, returns line-crossing events.
        """
        current_time = time.time()
        
        if raw_frame is not None:
            h, w = raw_frame.shape[:2]
            self.line_counter.width = float(w)
            self.line_counter.height = float(h)
        
        for obj in frame_data:
            tid = obj['track_id']
            if tid not in self.tracks:
                self.tracks[tid] = TrackState(track_id=tid, class_name=obj['class_name'])
            self.tracks[tid].update(obj['bbox'], obj['timestamp'])
            self.tracks[tid].class_name = obj['class_name'] 
            
        self.purge_stale_tracks(current_time)
        
        # Periodic throttle cache cleanup (every 60s)
        if current_time - self._last_cleanup > 60.0:
            alert_throttle.cleanup_stale()
            self._last_cleanup = current_time
        
        return self.evaluate_rules(raw_frame)
        
    def purge_stale_tracks(self, current_time: float, max_age: float = 3.0):
        stale_ids = [tid for tid, state in self.tracks.items() if current_time - state.last_updated > max_age]
        for tid in stale_ids:
            del self.tracks[tid]
 
    def evaluate_rules(self, raw_frame: np.ndarray):
        """
        Runs all enabled AI modules and fires alerts through the pipeline.
        
        Pipeline: Module detects → Throttle check → Alert logged immediately →
                  VLM enrichment runs async (non-blocking)
        """
        from backend.core.state import get_ai_modules
        
        active_modules = get_ai_modules(self.camera_id)
        all_alerts = []
        
        # ── Always-on modules (when any AI module is active) ──
        if active_modules:
            # ST-GLAD Spatial Graph Anomaly
            if 'stglad' in active_modules:
                from backend.ai.modules.st_glad import detect_st_glad_anomaly
                all_alerts.extend(detect_st_glad_anomaly(self.tracks, self.camera_id))

            # Fall detection — ONLY check when 'posture' (or a dedicated fall module) is enabled
            if 'posture' in active_modules:
                all_alerts.extend(detect_falls(self.tracks, self.camera_id))
            
            # Zone intrusion
            if 'intrusion' in active_modules:
                all_alerts.extend(detect_zone_intrusion(self.tracks, self.camera_id))
            
            # if "unattended_object" in active_mods:
            #     alerts.extend(detect_unattended_object(self.tracks, camera_id))
            
            # Slip / Trip Hazard (periodic full-frame VLM scan)
            if 'sliphazard' in active_modules:
                all_alerts.extend(detect_slip_hazard(self.camera_id, raw_frame))
        
        # ── Process alerts through throttle + VLM cascade ──
        self._process_alerts(all_alerts, raw_frame)
        
        # ── Line counting (independent of AI modules) ──
        self.ENABLE_LINE_COUNTING = True
        crossed_events = []
        if self.ENABLE_LINE_COUNTING:
            crossed_events = self.line_counter.evaluate(self.tracks)
            self.in_count = self.line_counter.in_count
            self.out_count = self.line_counter.out_count
            
            # Log gate events and trigger RE_ID
            for direction, tid in crossed_events:
                from backend.core import state as backend_state
                from backend.core.config_loader import loader
                from backend.ai.vlm_integration import enqueue_vlm_task
        return crossed_events
    
    def _process_alerts(self, alerts: List[dict], raw_frame: np.ndarray):
        """
        Process alert events through the pipeline:
        1. Throttle check — severity-tiered cooldown (CRITICAL=120s, HIGH=90s, WARNING=180s, LOW=300s)
        2. Save evidence screenshot — only for HIGH/CRITICAL; global hourly cap enforced
        3. Fire immediate alert to dashboard
        4. Enqueue VLM cascade for enrichment (async, non-blocking)
        """
        for alert in alerts:
            event_type = alert["event_type"]
            camera_id = alert["camera_id"]
            track_id = alert.get("track_id")
            bbox = alert.get("bbox")
            severity = alert["severity"]
            description = alert["description"]
            vlm_prompt = alert.get("vlm_prompt", "")
            # Full-scene events (e.g. ST-GLAD) should pass full frame to VLM, not a single crop
            vlm_use_full_frame = alert.get("vlm_use_full_frame", False)

            # 1. Throttle check — use severity-tiered cooldown
            cooldown = alert_throttle.get_cooldown_for_severity(severity)
            if alert_throttle.is_throttled(event_type, camera_id, track_id, cooldown):
                continue

            alert_throttle.record_fired(event_type, camera_id, track_id)

            # 2. Save evidence screenshot
            # Policy: only HIGH/CRITICAL get a screenshot; global hourly cap enforced inside throttle
            evidence_file = ""
            if raw_frame is not None:
                evidence_bbox = None if vlm_use_full_frame else bbox
                evidence_file = alert_throttle.save_evidence_screenshot(
                    camera_id, event_type, track_id, raw_frame, evidence_bbox,
                    severity=severity
                )

            # 3. Fire immediate alert to dashboard (real-time)
            from backend.core.config_loader import loader
            from backend.core.state import add_alert_log, trigger_highlight, update_camera_metrics, state_lock, shared_stats

            cam_info = loader.get_camera_details(camera_id)
            cam_name = cam_info.get("Name", f"Cam {camera_id}") if cam_info else f"Cam {camera_id}"

            vlm_status = "PENDING" if (vlm_prompt and raw_frame is not None) else "VERIFIED"
            log_entry = add_alert_log(camera_id, cam_name, event_type, severity, description, evidence_file, vlm_status)
            alert_id = log_entry.get("id") if log_entry else None

            # Highlight the target on live stream
            if track_id is not None:
                trigger_highlight(camera_id, track_id, 8.0)

            # Update dashboard camera alert state
            person_count = 0
            with state_lock:
                for cam in shared_stats.get("cameras", []):
                    if cam.get("id") == camera_id:
                        person_count = cam.get("person_count", 0)
                        break
            update_camera_metrics(camera_id, person_count, is_alert=True, alert_type=event_type)

            # 4. Enqueue VLM cascade for enrichment (async, non-blocking)
            if vlm_prompt and raw_frame is not None:
                try:
                    from backend.ai.vlm_integration import enqueue_vlm_task
                    # Full-frame events (ST-GLAD): pass bbox=None so VLM sees the whole scene
                    vlm_bbox = None if vlm_use_full_frame else bbox
                    
                    track_history = []
                    if track_id is not None and str(track_id) in self.tracks:
                        track_history = self.tracks[str(track_id)].bboxes

                    enqueue_vlm_task(camera_id, event_type, raw_frame, vlm_bbox, track_id, vlm_prompt, severity=severity, alert_id=alert_id, track_history=track_history)
                except Exception as e:
                    print(f"[EVENT MANAGER] VLM enqueue failed (non-blocking): {e}")

