import numpy as np

# ─── Per-camera cross-frame deduplication state ─────────────────────────────
# Used to suppress mirror/reflection ghost detections within a single camera.
# Key: camera_id → list of (cx, cy, frame_w, frame_h) from previous YOLO output
_prev_detections = {}


def _iou(boxA, boxB):
    """Compute Intersection-over-Union between two [x1,y1,x2,y2] boxes."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0.0
    aA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    aB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return inter / float(aA + aB - inter + 1e-6)


def _is_mirror_of(cx1, cy1, cx2, cy2, frame_w, frame_h, mirror_margin=0.08):
    """
    Returns True if box2 appears to be a horizontal or vertical mirror of box1.
    mirror_margin: fraction of frame dimension allowed as tolerance.
    """
    # Horizontal mirror: cx1 + cx2 ≈ frame_w  (symmetric about vertical axis)
    h_tol = frame_w * mirror_margin
    if abs((cx1 + cx2) - frame_w) < h_tol and abs(cy1 - cy2) < frame_h * 0.20:
        return True
    # Vertical mirror: cy1 + cy2 ≈ frame_h  (symmetric about horizontal axis)
    v_tol = frame_h * mirror_margin
    if abs((cy1 + cy2) - frame_h) < v_tol and abs(cx1 - cx2) < frame_w * 0.20:
        return True
    return False


def optimize_detections(results, min_height=15, max_height=2000,
                        min_aspect_ratio=0.15, max_aspect_ratio=8.0,
                        camera_id=None):
    """
    Advanced standalone filter module for raw YOLO bounding boxes.
    1. Height & aspect-ratio gate to remove tiny glitches and machine parts.
    2. Mirror / reflection deduplication — suppresses boxes that are
       geometrically symmetric about the frame centre (glass reflections,
       security mirrors, split-screen artefacts).
    3. Confidence-based NMS for boxes that heavily overlap (IoU > 0.55).
    """
    if results.boxes is None:
        return []

    frame_w = int(results.orig_shape[1]) if hasattr(results, 'orig_shape') else 416
    frame_h = int(results.orig_shape[0]) if hasattr(results, 'orig_shape') else 416

    has_keypoints = (hasattr(results, 'keypoints')
                     and results.keypoints is not None
                     and results.keypoints.data is not None)

    raw = []
    for i, box in enumerate(results.boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        tid = int(box.id[0]) if (box.id is not None) else -1

        box_w = x2 - x1
        box_h = y2 - y1

        # ── 1. Size gate ──────────────────────────────────────────────────────
        if box_h < min_height or box_h > max_height:
            continue
        # Must be at least 8 px wide
        if box_w < 8:
            continue

        # ── 2. Aspect ratio gate ──────────────────────────────────────────────
        aspect = box_h / float(box_w + 1e-6)
        if aspect < min_aspect_ratio or aspect > max_aspect_ratio:
            continue

        kpts = None
        if has_keypoints and len(results.keypoints.data) > i:
            kpts = results.keypoints.data[i].cpu().numpy()

        raw.append((x1, y1, x2, y2, conf, tid, kpts))

    if not raw:
        return []

    # ── 3. Mirror / reflection filter ────────────────────────────────────────
    # For each pair of detections, if one is a mirror image of the other,
    # keep only the higher-confidence one.
    keep_mask = [True] * len(raw)
    for i in range(len(raw)):
        if not keep_mask[i]:
            continue
        x1i, y1i, x2i, y2i, conf_i = raw[i][:5]
        cxi = (x1i + x2i) / 2.0
        cyi = (y1i + y2i) / 2.0
        for j in range(i + 1, len(raw)):
            if not keep_mask[j]:
                continue
            x1j, y1j, x2j, y2j, conf_j = raw[j][:5]
            cxj = (x1j + x2j) / 2.0
            cyj = (y1j + y2j) / 2.0

            if _is_mirror_of(cxi, cyi, cxj, cyj, frame_w, frame_h):
                # Suppress the lower-confidence detection
                if conf_i >= conf_j:
                    keep_mask[j] = False
                else:
                    keep_mask[i] = False
                    break  # box i is gone, no need to keep comparing

    filtered = [raw[i] for i in range(len(raw)) if keep_mask[i]]

    # ── 4. Heavy-overlap NMS (IoU > 0.55) ────────────────────────────────────
    # Handles cases where the tracker produces two near-identical boxes
    nms_keep = [True] * len(filtered)
    for i in range(len(filtered)):
        if not nms_keep[i]:
            continue
        for j in range(i + 1, len(filtered)):
            if not nms_keep[j]:
                continue
            iou = _iou(filtered[i][:4], filtered[j][:4])
            if iou > 0.55:
                if filtered[i][4] >= filtered[j][4]:
                    nms_keep[j] = False
                else:
                    nms_keep[i] = False
                    break

    return [filtered[i] for i in range(len(filtered)) if nms_keep[i]]