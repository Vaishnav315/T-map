import time
import threading

class WorkerTracker:
    def __init__(self, ghost_timeout=0.5, alpha=0.70):
        """
        alpha: Smoothing factor for Exponential Moving Average (EMA).
               Higher value = tighter adherence to raw coordinates (less lag).
               0.70 delivers responsive map movement.
        ghost_timeout: Grace retention window (in seconds). Keeps dots at their last
                       known coordinate if the model temporarily loses line of sight.
        """
        self._lock = threading.Lock()   # Thread-safety: protects all dicts below
        self.trails = {}            # Maps track_id -> list of clean GPS [lat, lng] arrays
        self.blueprint_trails = {}  # Maps track_id -> list of clean Blueprint [y, x] arrays
        self.last_seen = {}         # Maps track_id -> timestamp of last physical detection
        self.smoothed_pos = {}      # Maps track_id -> last smoothed GPS coordinate state
        self.smoothed_bp_pos = {}   # Maps track_id -> last smoothed Blueprint coordinate state
        self._trail_timestamps = {} # Maps track_id -> timestamps for sliding window windowing
        self.camera_locks = {}      # Maps track_id -> (camera_id, lock_expiry_time, bbox_area)
        self.velocities = {}        # Maps track_id -> (vy, vx) GPS velocity
        self.bp_velocities = {}     # Maps track_id -> (vy, vx) blueprint velocity
        self.ghost_timeout = ghost_timeout
        self.alpha = alpha

    def update(self, track_id, bp_coord, gps_coord, duration_limit_seconds, camera_id=None, bbox_area=0.0):
        if track_id == -1:
            return [], []

        with self._lock:
            now = time.time()

            # ── Camera Ownership Lock ────────────────────────────────
            # Prevent dot flickering when overlapping cameras both detect the same person.
            if camera_id is not None:
                lock_info = self.camera_locks.get(track_id)
                if lock_info:
                    locked_cam, expiry, locked_area = lock_info
                    if now < expiry and camera_id != locked_cam:
                        if bbox_area < 1.3 * locked_area:
                            return self.trails.get(track_id, []), self.blueprint_trails.get(track_id, [])
                self.camera_locks[track_id] = (camera_id, now + 1.0, bbox_area)

            # NOTE: Spatial deduplication was previously here but has been removed.
            # Cross-camera merging is now handled entirely by PositionReIDRegistry, which
            # assigns the SAME global_id to the same physical person across cameras BEFORE
            # any update reaches this tracker. Two different global_ids arriving here are
            # guaranteed to be genuinely different people and must NOT be merged.

            # ── Temporal Delta ───────────────────────────────────────
            dt = now - self.last_seen.get(track_id, now)

            # ── GPS Smoothing (EMA + Velocity Predictor) ─────────────
            if track_id in self.smoothed_pos:
                last_y, last_x = self.smoothed_pos[track_id]
                curr_y, curr_x = gps_coord
                if track_id in self.velocities and 0 < dt < 2.0:
                    last_vy, last_vx = self.velocities[track_id]
                    curr_vy = (curr_y - last_y) / dt
                    curr_vx = (curr_x - last_x) / dt
                    vy = 0.5 * curr_vy + 0.5 * last_vy
                    vx = 0.5 * curr_vx + 0.5 * last_vx
                    pred_y = last_y + vy * dt
                    pred_x = last_x + vx * dt
                    smooth_y = self.alpha * curr_y + (1.0 - self.alpha) * pred_y
                    smooth_x = self.alpha * curr_x + (1.0 - self.alpha) * pred_x
                    self.velocities[track_id] = (vy, vx)
                elif dt >= 2.0:
                    # Snapping: Person was occluded for a long time. Jump instantly.
                    smooth_y = curr_y
                    smooth_x = curr_x
                    self.velocities[track_id] = (0.0, 0.0)
                else:
                    smooth_y = self.alpha * curr_y + (1.0 - self.alpha) * last_y
                    smooth_x = self.alpha * curr_x + (1.0 - self.alpha) * last_x
                    self.velocities[track_id] = (
                        (curr_y - last_y) / dt if dt > 0 else 0.0,
                        (curr_x - last_x) / dt if dt > 0 else 0.0
                    )
                smoothed_coord = [smooth_y, smooth_x]
            else:
                smoothed_coord = list(gps_coord)
                self.trails[track_id] = []
                self._trail_timestamps[track_id] = []
                self.velocities[track_id] = (0.0, 0.0)

            self.smoothed_pos[track_id] = smoothed_coord
            self.last_seen[track_id] = now

            # ── Blueprint Smoothing (EMA + Velocity Predictor) ───────
            if track_id in self.smoothed_bp_pos:
                last_y, last_x = self.smoothed_bp_pos[track_id]
                curr_y, curr_x = bp_coord
                if track_id in self.bp_velocities and 0 < dt < 2.0:
                    last_vy, last_vx = self.bp_velocities[track_id]
                    curr_vy = (curr_y - last_y) / dt
                    curr_vx = (curr_x - last_x) / dt
                    vy = 0.5 * curr_vy + 0.5 * last_vy
                    vx = 0.5 * curr_vx + 0.5 * last_vx
                    pred_y = last_y + vy * dt
                    pred_x = last_x + vx * dt
                    smooth_y = self.alpha * curr_y + (1.0 - self.alpha) * pred_y
                    smooth_x = self.alpha * curr_x + (1.0 - self.alpha) * pred_x
                    self.bp_velocities[track_id] = (vy, vx)
                elif dt >= 2.0:
                    # Snapping: Person was occluded for a long time. Jump instantly.
                    smooth_y = curr_y
                    smooth_x = curr_x
                    self.bp_velocities[track_id] = (0.0, 0.0)
                else:
                    smooth_y = self.alpha * curr_y + (1.0 - self.alpha) * last_y
                    smooth_x = self.alpha * curr_x + (1.0 - self.alpha) * last_x
                    self.bp_velocities[track_id] = (
                        (curr_y - last_y) / dt if dt > 0 else 0.0,
                        (curr_x - last_x) / dt if dt > 0 else 0.0
                    )
                smoothed_bp = [smooth_y, smooth_x]
            else:
                smoothed_bp = list(bp_coord)
                self.blueprint_trails[track_id] = []
                self.bp_velocities[track_id] = (0.0, 0.0)

            self.smoothed_bp_pos[track_id] = smoothed_bp

            # ── Append to Trail ──────────────────────────────────────
            self.trails[track_id].append(smoothed_coord)
            self.blueprint_trails[track_id].append(smoothed_bp)
            self._trail_timestamps[track_id].append(now)

            # ── Sliding Window Trim ──────────────────────────────────
            valid_indices = [i for i, t in enumerate(self._trail_timestamps[track_id])
                             if now - t <= duration_limit_seconds]
            if valid_indices:
                self.trails[track_id] = [self.trails[track_id][i] for i in valid_indices]
                self.blueprint_trails[track_id] = [self.blueprint_trails[track_id][i] for i in valid_indices]
                self._trail_timestamps[track_id] = [self._trail_timestamps[track_id][i] for i in valid_indices]
            else:
                self.trails[track_id] = []
                self.blueprint_trails[track_id] = []
                self._trail_timestamps[track_id] = []

            return self.trails[track_id], self.blueprint_trails[track_id]

    def get_ghost_positions(self, active_tids, duration_limit_seconds):
        """
        Collects and retains positions for targets that went missing in the current frame,
        preventing dots from flashing off the map layout.
        """
        with self._lock:
            now = time.time()
            ghosts = []

            for tid, last_t in list(self.last_seen.items()):
                if tid in active_tids or tid == -1:
                    continue
                if now - last_t <= self.ghost_timeout:
                    if tid in self.smoothed_pos and tid in self.trails:
                        valid_indices = [i for i, t in enumerate(self._trail_timestamps.get(tid, []))
                                         if now - t <= duration_limit_seconds]
                        if valid_indices:
                            self.trails[tid] = [self.trails[tid][i] for i in valid_indices]
                            self.blueprint_trails[tid] = [self.blueprint_trails[tid][i] for i in valid_indices]
                            self._trail_timestamps[tid] = [self._trail_timestamps[tid][i] for i in valid_indices]

                        ghosts.append({
                            "id": tid,
                            "pos": self.smoothed_pos[tid],
                            "blueprint_pos": self.smoothed_bp_pos.get(tid),
                            "trail": self.trails[tid],
                            "blueprint_trail": self.blueprint_trails.get(tid, []),
                            "is_ghost": True
                        })
            return ghosts

    def cleanup(self):
        """
        Garbage collect tracks that have left the scene completely.
        Prunes all stale entries from every internal dict.
        """
        with self._lock:
            now = time.time()
            stale_ids = [tid for tid, t in list(self.last_seen.items())
                         if now - t > self.ghost_timeout]
            for tid in stale_ids:
                for d in [self.trails, self.blueprint_trails, self.last_seen,
                           self.smoothed_pos, self.smoothed_bp_pos,
                           self._trail_timestamps, self.camera_locks,
                           self.velocities, self.bp_velocities]:
                    d.pop(tid, None)