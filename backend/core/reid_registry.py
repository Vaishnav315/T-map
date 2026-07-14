import time
import threading
import json
import cv2
import numpy as np
from backend.core import database
from backend.core import state

# HSV color range boundaries for dominant clothing color heuristic
# H: 0-180, S: 0-255, V: 0-255
COLOR_RANGES = {
    "black": [((0, 0, 0), (180, 255, 55))],
    "white": [((0, 0, 195), (180, 50, 255))],
    "grey": [((0, 0, 55), (180, 50, 195))],
    "red": [((0, 50, 50), (10, 255, 255)), ((170, 50, 50), (180, 255, 255))],
    "orange": [((10, 50, 50), (25, 255, 255))],
    "yellow": [((25, 50, 50), (35, 255, 255))],
    "green": [((35, 50, 50), (85, 255, 255))],
    "blue": [((85, 50, 50), (130, 255, 255))],
    "purple": [((130, 50, 50), (160, 255, 255))],
    "pink": [((160, 50, 50), (170, 255, 255))],
    "brown": [((10, 50, 30), (20, 255, 150))]
}

def classify_region_color(hsv_img):
    if hsv_img is None or hsv_img.size == 0:
        return "unknown"
    
    best_color = "unknown"
    max_pixels = 0
    total_pixels = hsv_img.shape[0] * hsv_img.shape[1]
    
    for color_name, ranges in COLOR_RANGES.items():
        mask = None
        for lower, upper in ranges:
            m = cv2.inRange(hsv_img, np.array(lower), np.array(upper))
            if mask is None:
                mask = m
            else:
                mask = cv2.bitwise_or(mask, m)
        count = np.sum(mask > 0)
        if count > max_pixels:
            max_pixels = count
            best_color = color_name
            
    # Default to unknown if coverage is extremely low
    if max_pixels < 0.05 * total_pixels:
        return "unknown"
    return best_color

def extract_cv_signature(crop):
    """
    Extracts the lightweight visual signature:
    - Dominant colors for top and bottom halves (microsecond execution)
    - Compact 8x8 Hue-Saturation histograms
    """
    if crop is None or crop.size == 0:
        return None
    
    try:
        h, w = crop.shape[:2]
        # Crop clothing sections to avoid head/hair (15%-50%) and shoes (55%-90%)
        upper_crop = crop[int(h*0.15):int(h*0.50), :]
        lower_crop = crop[int(h*0.55):int(h*0.90), :]
        
        if upper_crop.size == 0 or lower_crop.size == 0:
            return None
        
        hsv_upper = cv2.cvtColor(upper_crop, cv2.COLOR_BGR2HSV)
        hsv_lower = cv2.cvtColor(lower_crop, cv2.COLOR_BGR2HSV)
        
        top_color = classify_region_color(hsv_upper)
        bottom_color = classify_region_color(hsv_lower)
        
        # Calculate HS histograms (8 Hue bins, 8 Saturation bins)
        hist_upper = cv2.calcHist([hsv_upper], [0, 1], None, [8, 8], [0, 180, 0, 256])
        hist_lower = cv2.calcHist([hsv_lower], [0, 1], None, [8, 8], [0, 180, 0, 256])
        
        cv2.normalize(hist_upper, hist_upper, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist_lower, hist_lower, 0, 1, cv2.NORM_MINMAX)
        
        # Removed color-based heuristics as requested by user. We will rely entirely on 
        # behavioral ReID (pacing back and forth, or 3+ crossings) to exclude the guard.
             
        return {
            "top_color": top_color,
            "bottom_color": bottom_color,
            "hist_upper": hist_upper,
            "hist_lower": hist_lower,
            "is_uniform": False
        }
    except Exception as e:
        print(f"[CV-SIGNATURE ERROR] Failed to extract signature: {e}")
        return None

def compare_cv_signatures(sig1, sig2):
    if sig1 is None or sig2 is None:
        return 0.0
    
    # Calculate histogram correlation
    corr_upper = cv2.compareHist(sig1["hist_upper"], sig2["hist_upper"], cv2.HISTCMP_CORREL)
    corr_lower = cv2.compareHist(sig1["hist_lower"], sig2["hist_lower"], cv2.HISTCMP_CORREL)
    
    # Average correlation (-1.0 to 1.0 -> map to 0.0 to 1.0)
    score_hist = max(0.0, (corr_upper + corr_lower) / 2.0)
    
    # Semantic color match weight
    color_match = 0.0
    if sig1["top_color"] == sig2["top_color"]:
        color_match += 0.5
    if sig1["bottom_color"] == sig2["bottom_color"]:
        color_match += 0.5
        
    return 0.7 * score_hist + 0.3 * color_match


class ReIDRegistry:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_profiles = {}  # global_id -> { 'signature': {}, 'cv_signature': {}, 'last_cam': '', 'last_time': 0, 'path': [] }
        self.camera_exits = []     # List of { 'global_id', 'camera_id', 'timestamp', 'signature', 'cv_signature' }
        self.next_global_id = 1
        self.guard_ids = set()
        
        # Maps (camera_id, track_id) -> (assigned_global_id, timestamp) to coordinate fast CV match with async VLM refinement
        self.fast_match_cache = {}

    def calculate_similarity(self, sig1, sig2):
        score = 0
        if sig1.get("top_color", "").lower() == sig2.get("top_color", "").lower(): score += 1
        if sig1.get("bottom_color", "").lower() == sig2.get("bottom_color", "").lower(): score += 1
        if sig1.get("is_uniform") == sig2.get("is_uniform"): score += 1
        return score

    def register_continuous_cv(self, camera_id, tid, cv_sig):
        """
        Continuous Multi-Camera Tracking Matcher. Called when a new tid appears in a camera stream.
        Caches the global_id so it doesn't need to be extracted every frame.
        """
        if cv_sig is None:
            return None

        with self.lock:
            now = time.time()
            # Purge fast match cache every 30s (not 300s) so stale tid->global_id
            # mappings from previous video loops don't block correct re-matching.
            self.fast_match_cache = {k: v for k, v in self.fast_match_cache.items() if now - v[1] < 30.0}

            # If already cached within 30s, return
            cached = self.fast_match_cache.get((camera_id, tid))
            if cached:
                return cached[0]

            best_match = None
            best_score = -1.0

            signature = {
                "top_color": cv_sig["top_color"],
                "bottom_color": cv_sig["bottom_color"],
                "is_uniform": cv_sig["is_uniform"]
            }

            # Purge profiles not refreshed in 60s to prevent unbounded accumulation
            stale_gids = [gid for gid, p in self.active_profiles.items()
                          if now - p.get('last_seen', now) > 60.0]
            for gid in stale_gids:
                del self.active_profiles[gid]

            # Compare against recently active profiles
            for global_id, profile in self.active_profiles.items():
                if profile.get('cv_signature') is not None:
                    score = compare_cv_signatures(cv_sig, profile['cv_signature'])
                else:
                    score = self.calculate_similarity(signature, profile['signature']) / 3.0

                if score > best_score:
                    best_score = score
                    best_match = global_id

            # Lowered from 0.70 to 0.45: the same person viewed from different angles
            # always produces a lower appearance similarity score, so a strict threshold
            # causes false "new person" creation across co-located cameras.
            if best_match is not None and best_score >= 0.45:
                assigned_global_id = best_match
                # Refresh last_seen so this profile doesn't get purged while still active
                if assigned_global_id in self.active_profiles:
                    self.active_profiles[assigned_global_id]['last_seen'] = now
            else:
                assigned_global_id = self.next_global_id
                self.next_global_id += 1
                self.active_profiles[assigned_global_id] = {
                    'signature': signature,
                    'cv_signature': cv_sig,
                    'path': [camera_id],
                    'last_seen': now
                }

            # Store in cache
            self.fast_match_cache[(camera_id, tid)] = (assigned_global_id, now)
            return assigned_global_id

    def register_gate_crossing_cv(self, camera_id, tid, direction, cv_sig):
        """
        Fast Level-0 Matcher. Called synchronously on gate crossing.
        Returns: (assigned_global_id, needs_vlm_escalation)
        """
        if cv_sig is None:
            return None, True
            
        with self.lock:
            now = time.time()
            assigned_global_id = None
            needs_vlm = True
            
            signature = {
                "top_color": cv_sig["top_color"],
                "bottom_color": cv_sig["bottom_color"],
                "is_uniform": cv_sig["is_uniform"]
            }
            
            # Clean up old fast match cache entries older than 5 minutes
            self.fast_match_cache = {k: v for k, v in self.fast_match_cache.items() if now - v[1] < 300.0}
            
            if direction == "IN":
                best_match = None
                best_score = -1.0
                
                valid_exits = [e for e in self.camera_exits if now - e['timestamp'] < 90.0]
                self.camera_exits = valid_exits
                
                for exit_record in valid_exits:
                    if exit_record['camera_id'] != camera_id:
                        if exit_record.get('cv_signature') is not None:
                            score = compare_cv_signatures(cv_sig, exit_record['cv_signature'])
                        else:
                            score = self.calculate_similarity(signature, exit_record['signature']) / 3.0
                            
                        if score > best_score:
                            best_score = score
                            best_match = exit_record['global_id']
                
                # Decision Tree
                if best_match is not None and best_score >= 0.75:
                    assigned_global_id = best_match
                    needs_vlm = False  # Clear high-confidence match! Skip heavy VLM
                    print(f"[D-MCST RE-ID] Fast Match Confirmed! Target #{tid} on Cam {camera_id} mapped to Global ID {assigned_global_id} (Sim: {best_score:.2f}). Bypassing VLM.")
                elif best_match is not None and best_score >= 0.40:
                    assigned_global_id = best_match
                    needs_vlm = True   # Ambiguous, request VLM refinement
                    print(f"[D-MCST RE-ID] Ambiguous Match! Target #{tid} mapped to Global ID {assigned_global_id} (Sim: {best_score:.2f}). Escalate to VLM.")
                else:
                    assigned_global_id = self.next_global_id
                    self.next_global_id += 1
                    needs_vlm = False  # VLM is completely disabled for gate counting
                    
                    self.active_profiles[assigned_global_id] = {
                        'signature': signature,
                        'cv_signature': cv_sig,
                        'path': []
                    }
                    print(f"[D-MCST RE-ID] New unique person identified via CV. Assigned Global ID {assigned_global_id}. Signature: {signature}")
                
                # Update path tracking
                if assigned_global_id in self.active_profiles:
                    profile = self.active_profiles[assigned_global_id]
                    if not profile['path'] or profile['path'][-1] != camera_id:
                        profile['path'].append(camera_id)
                    
                    # Cyclic guard patrol suppression check (applies to anyone now, regardless of uniform)
                    is_guard = False
                    if len(profile['path']) >= 3 and assigned_global_id not in self.guard_ids:
                        is_guard = True
                        self.guard_ids.add(assigned_global_id)
                        print(f"[D-MCST RE-ID] Cyclic guard patrol detected for Global ID {assigned_global_id}. Suppressing from counts and retroactively correcting.")
                        
                        # Retroactively fix the previous 2 false counts!
                        with state.state_lock:
                            # They must have crossed IN at least once and OUT at least once to get a path of 3.
                            state.shared_stats['global_gate_in'] = max(0, state.shared_stats['global_gate_in'] - 1)
                            state.shared_stats['global_gate_out'] = max(0, state.shared_stats['global_gate_out'] - 1)
                            database.delete_last_gate_event("IN")
                            database.delete_last_gate_event("OUT")
                else:
                    is_guard = False
                
                if assigned_global_id in self.guard_ids:
                    is_guard = True
                    
                # Increment global counts
                if best_match is None and not is_guard:
                    with state.state_lock:
                        state.shared_stats['global_gate_in'] += 1
                        database.insert_gate_event("IN", 0.0, 0.0)
                        print(f"[D-MCST RE-ID] Clean Entrance Confirmed. Global Gate IN: {state.shared_stats['global_gate_in']}")
                        
            elif direction == "OUT":
                assigned_global_id = self.next_global_id
                self.next_global_id += 1
                needs_vlm = False
                
                self.camera_exits.append({
                    'global_id': assigned_global_id,
                    'camera_id': camera_id,
                    'timestamp': now,
                    'signature': signature,
                    'cv_signature': cv_sig
                })
                
                print(f"[D-MCST RE-ID] Target #{tid} exited Cam {camera_id}. Logged for cross-cam transition matching. Signature: {signature}")
                
                is_guard = assigned_global_id in self.guard_ids
                    
                if not is_guard:
                    with state.state_lock:
                        state.shared_stats['global_gate_out'] += 1
                        database.insert_gate_event("OUT", 0.0, 0.0)
            
            # Cache the tracking ID mapping for VLM callback coordination
            self.fast_match_cache[(camera_id, tid)] = (assigned_global_id, now)
            return assigned_global_id, needs_vlm

    def process_gate_crossing(self, camera_id, tid, direction, signature_text):
        """
        VLM Enrichment Callback. Refines/corrects the registry profile once VLM finishes.
        """
        try:
            signature = json.loads(signature_text)
        except:
            signature = {"top_color": "unknown", "bottom_color": "unknown", "is_uniform": False}
            
        with self.lock:
            now = time.time()
            
            # Check if this crossing was already registered by the Level-0 fast matcher
            fast_match = self.fast_match_cache.get((camera_id, tid))
            if fast_match:
                assigned_global_id = fast_match[0]
                print(f"[D-MCST RE-ID VLM-Enrich] Refined Global ID {assigned_global_id} with VLM Semantics: {signature}")
                
                if assigned_global_id in self.active_profiles:
                    # Update rich signature from VLM
                    self.active_profiles[assigned_global_id]['signature'] = signature
                    profile = self.active_profiles[assigned_global_id]
                    
                    # Update path and recheck guard uniform status
                    if signature.get("is_uniform", False) or "security" in signature_text.lower() or "guard" in signature_text.lower():
                        if len(profile['path']) >= 3 and assigned_global_id not in self.guard_ids:
                            self.guard_ids.add(assigned_global_id)
                            print(f"[D-MCST RE-ID VLM-Enrich] Cyclic guard patrol confirmed for Global ID {assigned_global_id} via VLM.")
                            
                            # Revert the count that was erroneously incremented by the fast matcher
                            from backend.core import state
                            with state.state_lock:
                                if direction == "IN":
                                    state.shared_stats['global_gate_in'] = max(0, state.shared_stats['global_gate_in'] - 1)
                                    database.delete_last_gate_event("IN")
                                elif direction == "OUT":
                                    state.shared_stats['global_gate_out'] = max(0, state.shared_stats['global_gate_out'] - 1)
                                    database.delete_last_gate_event("OUT")
                return
                
            # Fallback if CV register was skipped/failed
            assigned_global_id = self.next_global_id
            self.next_global_id += 1
            self.active_profiles[assigned_global_id] = {
                'signature': signature,
                'path': []
            }
            print(f"[D-MCST RE-ID VLM-Fallback] Registered New Global ID {assigned_global_id} via VLM: {signature}")
            
            is_guard = signature.get("is_uniform", False) or "security" in signature_text.lower() or "guard" in signature_text.lower()
            if not is_guard:
                from backend.core import state
                with state.state_lock:
                    if direction == "IN":
                        state.shared_stats['global_gate_in'] += 1
                        database.insert_gate_event("IN", 0.0, 0.0)
                    elif direction == "OUT":
                        state.shared_stats['global_gate_out'] += 1
                        database.insert_gate_event("OUT", 0.0, 0.0)


global_reid_registry = ReIDRegistry()


# ══════════════════════════════════════════════════════════════════════════════
#  BLUEPRINT-POSITION-BASED CROSS-CAMERA ReID
#  ─────────────────────────────────────────────────────────────────────────────
#  Replaces appearance-based (clothing color) ReID for uniform environments.
#
#  Algorithm:
#  1. Each per-camera ByteTrack local tid maps to a stable global_id.
#  2. A global_id is assigned by finding the closest PREDICTED position in
#     blueprint space (Leaflet pixel coordinates, shared across all cameras).
#  3. Prediction uses velocity-smoothed dead reckoning: where would this person
#     be NOW given their last known position and walking speed?
#  4. If the closest predicted position is within SPATIAL_THRESHOLD pixels,
#     it's the same person. Otherwise it's a new person.
#  5. Stale tracks (not seen for TRACK_TIMEOUT seconds) are garbage collected.
#
#  Key properties:
#  ✅ Immune to uniform/clothing color
#  ✅ Works for overlapping cameras (same physical area → same blueprint spot)
#  ✅ Works for sequential cameras (person walks across zones)
#  ✅ Fast: O(N) per detection where N = number of active people on site
#  ✅ No VLM, no image cropping, no histogram comparison needed
# ══════════════════════════════════════════════════════════════════════════════

class PositionReIDRegistry:
    """
    Blueprint-position-based cross-camera ReID system.
    Designed for environments where all workers wear identical uniforms.

    Frame isolation strategy:
    - begin_frame(camera_id) MUST be called at the start of each camera's
      inference pass. It resets the per-frame assignment set so that within
      a single frame, no two different YOLO track IDs can map to the same
      global_id. This correctly handles grouped/meeting scenarios.
    - Between frames, a NEW YOLO tid CAN match an existing global_id freely
      (no time restriction). This handles ByteTrack tid reassignment correctly.
    """

    # Maximum Leaflet-pixel distance to match a detection to an existing track.
    # Must cover the max calibration offset between co-located cameras (~50px)
    # plus movement between frames at normal walking speed (~30px).
    # Drastically increased to 400 to absorb extreme y2 (feet) fluctuations
    SPATIAL_THRESHOLD = 400

    # How long (seconds) to cache a (camera_id, tid) → global_id mapping.
    CACHE_TTL = 10

    # How long (seconds) without a detection before a track is deleted.
    # Set to 2s to perfectly match ghost_timeout in WorkerTracker.
    TRACK_TIMEOUT = 2

    def __init__(self):
        self._lock = threading.Lock()

        # global_id → track state
        # { 'bp_pos': [y, x], 'vel': [vy, vx], 'last_seen': float, 'cam_id': str }
        self._tracks = {}

        # (camera_id_str, tid_int) → (global_id, timestamp)
        self._cache = {}

        # camera_id_str → set of global_ids already assigned in the CURRENT frame.
        # Cleared by begin_frame(). Prevents two detections in one frame → same global_id.
        self._frame_used = {}

        self._next_id = 1

    # ── Public API ─────────────────────────────────────────────────────────────

    def begin_frame(self, camera_id):
        """
        Call ONCE at the start of each camera inference frame, before the
        detection loop. Resets the per-frame assignment set for this camera.
        """
        with self._lock:
            self._frame_used[str(camera_id)] = set()

    def register(self, camera_id, tid, bp_coord):
        """
        Assigns a stable global_id to a detection based on blueprint position.

        Args:
            camera_id: Camera identifier (str or int)
            tid:       ByteTrack local track ID (int)
            bp_coord:  [y, x] in Leaflet pixels from map_video_to_leaflet()

        Returns:
            global_id (int), or None if bp_coord is invalid.
        """
        if not bp_coord or bp_coord == [0, 0]:
            return None

        cam_str = str(camera_id)
        tid_int = int(tid)

        with self._lock:
            now = time.time()
            used = self._frame_used.get(cam_str, set())

            # ── Fast path: same camera+tid cached recently ─────────────────────
            cache_key = (cam_str, tid_int)
            cached = self._cache.get(cache_key)
            if cached is not None:
                gid, cached_at = cached
                if now - cached_at < self.CACHE_TTL and gid in self._tracks:
                    if gid not in used:
                        self._update(gid, bp_coord, cam_str, now)
                        used.add(gid)
                        self._frame_used[cam_str] = used
                        self._cache[cache_key] = (gid, now)
                        return gid
                    else:
                        # Collision: Another detection in this frame already claimed this ID 
                        # (likely via spatial match). Invalidate cache and fall through.
                        del self._cache[cache_key]

            # ── Spatial matching: find closest predicted position ───────────────
            best_gid  = None
            best_dist = float('inf')

            for gid, track in self._tracks.items():
                # Skip tracks already assigned to a different detection in this frame
                if gid in used:
                    continue

                dt = now - track['last_seen']
                if dt > self.TRACK_TIMEOUT:
                    continue

                # Dead-reckoning: predict where this person would be now
                # CRITICAL: Cap dead-reckoning at 1.5s max to prevent huge overshoots
                # if a person stops moving while occluded.
                effective_dt = min(dt, 1.5)
                vy, vx = track['vel']
                pred_y  = track['bp_pos'][0] + vy * effective_dt
                pred_x  = track['bp_pos'][1] + vx * effective_dt

                dy   = bp_coord[0] - pred_y
                dx   = bp_coord[1] - pred_x
                dist = (dy * dy + dx * dx) ** 0.5

                if dist < best_dist:
                    best_dist = dist
                    best_gid  = gid

            if best_gid is not None and best_dist <= self.SPATIAL_THRESHOLD:
                # ── Matched an existing person ────────────────────────────────
                self._update(best_gid, bp_coord, cam_str, now)
                used.add(best_gid)
                self._frame_used[cam_str] = used
                self._cache[cache_key] = (best_gid, now)
                return best_gid
            else:
                # ── New person entering the scene ─────────────────────────────
                gid = self._next_id
                self._next_id += 1
                self._tracks[gid] = {
                    'bp_pos':    list(bp_coord),
                    'vel':       [0.0, 0.0],
                    'last_seen': now,
                    'cam_id':    cam_str,
                }
                used.add(gid)
                self._frame_used[cam_str] = used
                self._cache[cache_key] = (gid, now)
                return gid

    def cleanup(self):
        """Remove expired tracks and cache entries."""
        with self._lock:
            now = time.time()
            stale = [gid for gid, t in list(self._tracks.items())
                     if now - t['last_seen'] > self.TRACK_TIMEOUT]
            for gid in stale:
                del self._tracks[gid]

            self._cache = {k: v for k, v in self._cache.items()
                           if now - v[1] < self.CACHE_TTL}

    def get_active_count(self):
        """Returns the number of people currently tracked across all cameras."""
        now = time.time()
        with self._lock:
            return sum(1 for t in self._tracks.values()
                       if now - t['last_seen'] < self.TRACK_TIMEOUT)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _update(self, gid, bp_coord, cam_str, now):
        """Update position and velocity of an existing track."""
        track = self._tracks[gid]
        dt = now - track['last_seen']

        if 0 < dt < 2.0:
            # Calculate instantaneous velocity and smooth with EMA (α=0.4)
            new_vy = (bp_coord[0] - track['bp_pos'][0]) / dt
            new_vx = (bp_coord[1] - track['bp_pos'][1]) / dt
            old_vy, old_vx = track['vel']
            track['vel'] = [
                0.4 * new_vy + 0.6 * old_vy,
                0.4 * new_vx + 0.6 * old_vx,
            ]

        track['bp_pos']    = list(bp_coord)
        track['last_seen'] = now
        track['cam_id']    = cam_str


# Singleton used by streamer.py for all position-based cross-camera ReID
position_reid_registry = PositionReIDRegistry()
