import numpy as np
import time
from typing import Dict, List

# History and sustained spike tracking per camera
_camera_energy_history: Dict[str, list] = {}
_camera_spike_counter: Dict[str, int] = {}

SPIKE_SUSTAIN_REQUIRED = 3  # Must exceed threshold for this many consecutive frames before alert fires

def reset_st_glad_counter(camera_id: str):
    global _camera_energy_history, _camera_spike_counter
    camera_id = str(camera_id)
    _camera_energy_history[camera_id] = []
    _camera_spike_counter[camera_id] = 0


def detect_st_glad_anomaly(tracks: Dict, camera_id: str, distance_sigma: float = 180.0) -> List[dict]:
    """
    Spatio-Temporal Graph Laplacian Anomaly Detection (ST-GLAD) — Realistic Mode

    Treats all active person tracks as nodes in a spatial graph.
    Builds a weighted adjacency matrix W combining:
      - Spatial affinity (Gaussian kernel on Euclidean distance)
      - Kinematic convergence factor (relative approach velocity)

    Computes eigenvalues of the Graph Laplacian L = D - W.
    Spectral Graph Energy = sum(λ²).

    An alert fires ONLY when:
      1. ≥ 3 people are actively tracked (n >= 3)
      2. Enough baseline history exists (≥ 20 frames)
      3. The energy spike exceeds mean + 4σ AND absolute > 2.0 (avoids noise)
      4. The spike is sustained for SPIKE_SUSTAIN_REQUIRED consecutive frames

    The VLM receives the FULL SCENE FRAME (bbox=None) and a concrete prompt
    describing the specific anomaly so it can make a meaningful decision.
    """
    alerts = []
    current_time = time.time()

    # --- 1. Extract valid, active tracks ---
    positions = []
    velocities = []
    valid_tids = []

    for tid, state in tracks.items():
        # Only include recently updated tracks with enough history
        if current_time - state.last_updated > 1.0:
            continue
        if len(state.bboxes) < 5:
            continue

        bbox = state.bboxes[-1]
        cx = (bbox[0] + bbox[2]) / 2
        cy = bbox[3]  # Use foot-point for ground-plane accuracy
        positions.append([cx, cy])
        velocities.append([state.vx, state.vy])
        valid_tids.append(tid)

    n = len(valid_tids)

    # Require at least 3 people for a meaningful graph
    if n < 3:
        # Reset sustained spike counter if not enough people
        _camera_spike_counter[camera_id] = 0
        return alerts

    P = np.array(positions, dtype=np.float64)
    V = np.array(velocities, dtype=np.float64)

    # --- 2. Build Weighted Adjacency Matrix W ---
    W = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            diff = P[i] - P[j]
            dist = np.linalg.norm(diff)

            # Spatial affinity: Gaussian kernel
            spatial_affinity = np.exp(-(dist ** 2) / (2 * distance_sigma ** 2))

            # Kinematic convergence: are they moving towards each other?
            v_rel = V[i] - V[j]
            dot_prod = np.dot(v_rel, diff)

            convergence_factor = 1.0
            if dist > 1e-5 and dot_prod < 0:
                approach_speed = -dot_prod / dist
                # Bounded scaling to prevent runaway values
                convergence_factor += min(approach_speed / 25.0, 3.0)

            w_ij = spatial_affinity * convergence_factor
            W[i, j] = w_ij
            W[j, i] = w_ij

    # --- 3. Graph Laplacian & Spectral Energy ---
    degree = np.sum(W, axis=1)
    D = np.diag(degree)
    L = D - W

    # eigh is optimised for real symmetric matrices
    eigenvalues = np.linalg.eigvalsh(L)
    graph_energy = float(np.sum(eigenvalues ** 2))

    # --- 4. Rolling baseline (45 frames) ---
    if camera_id not in _camera_energy_history:
        _camera_energy_history[camera_id] = []
    if camera_id not in _camera_spike_counter:
        _camera_spike_counter[camera_id] = 0

    history = _camera_energy_history[camera_id]
    history.append(graph_energy)

    if len(history) > 45:
        history.pop(0)

    # Debug print removed

    # Need at least 20 baseline frames before any decision
    if len(history) < 20:
        _camera_spike_counter[camera_id] = 0
        return alerts

    # Use older frames as baseline to let the spike stand out clearly
    baseline = history[:-3]
    mean_e = float(np.mean(baseline))
    std_e = float(np.std(baseline))

    # --- 5. Anomaly gate: strict 4-sigma + absolute floor ---
    threshold = mean_e + 4.0 * std_e
    is_spiking = graph_energy > threshold and graph_energy > 2.0

    if is_spiking:
        _camera_spike_counter[camera_id] = _camera_spike_counter.get(camera_id, 0) + 1
        # Debug print removed
    else:
        # Decay: reset on non-spike frame
        _camera_spike_counter[camera_id] = 0
        return alerts

    # --- 6. Only fire after sustained spike ---
    if _camera_spike_counter[camera_id] < SPIKE_SUSTAIN_REQUIRED:
        return alerts

    # --- 7. Build alert ---
    # Identify which node drives the anomaly (highest degree centrality)
    primary_idx = int(np.argmax(degree))
    primary_tid = valid_tids[primary_idx]
    primary_bbox = tracks[primary_tid].bboxes[-1]

    # Compute mean pairwise approach speed for a richer description
    approach_speeds = []
    for i in range(n):
        for j in range(i + 1, n):
            diff = P[i] - P[j]
            dist_ij = np.linalg.norm(diff)
            if dist_ij > 1e-5:
                v_rel = V[i] - V[j]
                dot_ij = np.dot(v_rel, diff)
                if dot_ij < 0:
                    approach_speeds.append(-dot_ij / dist_ij)
    mean_approach = float(np.mean(approach_speeds)) if approach_speeds else 0.0

    alert_desc = (
        f"ST-GLAD Graph Spectral Anomaly: {n} people detected with abnormal spatial interaction "
        f"(Energy {graph_energy:.2f} vs baseline {mean_e:.2f} ± {std_e:.2f}, "
        f"sustained {_camera_spike_counter[camera_id]} frames, "
        f"mean approach speed {mean_approach:.1f} px/s)."
    )

    vlm_prompt = (
        f"You are a security AI reviewing a full CCTV scene frame. "
        f"The mathematical graph analysis detected that {n} people in this scene have "
        f"suddenly changed their spatial dynamics — either rapidly converging on each other, "
        f"scattering in panic, or entering an abnormally close cluster. "
        f"The spectral graph energy spiked from a baseline of {mean_e:.1f} to {graph_energy:.1f}. "
        f"Look at the ENTIRE scene (not just one person) and determine: "
        f"Is there a genuine crowd anomaly, panic, dangerous convergence, or hazardous grouping occurring? "
        f"Reply YES or NO first, then explain in one sentence what you see."
    )

    alerts.append({
        "event_type": "SPATIAL_ANOMALY",
        "camera_id": camera_id,
        "track_id": primary_tid,
        "bbox": primary_bbox,
        # Signal to _process_alerts that VLM must use the full frame
        "vlm_use_full_frame": True,
        "severity": "CRITICAL",
        "description": alert_desc,
        "vlm_prompt": vlm_prompt,
    })

    # Reset history and spike counter to enforce cooldown
    _camera_energy_history[camera_id] = []
    _camera_spike_counter[camera_id] = 0

    return alerts
