import cv2
import numpy as np
from config_loader import loader

# ══════════════════════════════════════════════════════════════════
#  GLOBAL DIMENSIONS DEFINITIONS
# ══════════════════════════════════════════════════════════════════

# The video frame size the user took coordinates from (768x432)
CALIB_VIDEO_W, CALIB_VIDEO_H = 768.0, 432.0

# Final targeted container resolution inside React Leaflet
LEAFLET_MAP_W, LEAFLET_MAP_H = 2048.0, 1290.0

# ---------------------------------------------------------
# NEW LOGIC FROM HOMOGRAPHY.PY
# ---------------------------------------------------------

pts_video = np.float32([
    [111, 329],  # Landmark 1 (Front-Left)
    [631, 106],  # Landmark 2 (Back-Right)
    [304, 105],  # Landmark 3 (Back-Left)
    [755, 235]   # Landmark 4 (Front-Right)
])

pts_map_paint = np.float32([
    [496, 572],  # Landmark 1 matching spot
    [453, 544],  # Landmark 2 matching spot
    [442, 575],  # Landmark 3 matching spot
    [487, 546]   # Landmark 4 matching spot
])

# Create transform from User's Video Screenshot -> User's Map Screenshot
H_MATRIX = cv2.getPerspectiveTransform(pts_video, pts_map_paint)

def get_h_matrix():
    return H_MATRIX

def map_video_to_leaflet(camera_id, raw_x, raw_y, frame_w, frame_h):
    """
    Transforms a point from the camera stream perspective 
    into the [Y, X] coordinate array for Leaflet.
    """
    # 1. Scale the raw YOLO coordinate to match the calibration video dimensions
    scaled_video_x = raw_x * (CALIB_VIDEO_W / float(frame_w))
    scaled_video_y = raw_y * (CALIB_VIDEO_H / float(frame_h))

    # 2. Apply Homography to map directly to Leaflet space (except Y is not inverted yet)
    src_point = np.array([[[scaled_video_x, scaled_video_y]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(src_point, H_MATRIX)
    map_x = transformed[0][0][0]
    map_y = transformed[0][0][1]
    
    # 3. Invert Y for Leaflet (Leaflet Y=0 is bottom, image Y=0 is top)
    leaflet_x = round(map_x, 2)
    leaflet_y = round(LEAFLET_MAP_H - map_y, 2)
    
    return [leaflet_y, leaflet_x]

def map_leaflet_to_video(camera_id, leaflet_y, leaflet_x):
    # Reverse Step 3
    map_y = LEAFLET_MAP_H - leaflet_y
    map_x = leaflet_x

    # Reverse Step 2
    src = np.array([[[map_x, map_y]]], dtype=np.float32)
    H_inv = np.linalg.inv(H_MATRIX)
    dst = cv2.perspectiveTransform(src, H_inv)
    
    # Reverse Step 1 (Assume frame is 640x360 for default)
    raw_x = dst[0][0][0] / (CALIB_VIDEO_W / 640.0)
    raw_y = dst[0][0][1] / (CALIB_VIDEO_H / 360.0)
    return [float(raw_x), float(raw_y)]

def get_blueprint_coords(leaflet_y, leaflet_x):
    # Kept for compatibility with other cameras if needed
    return [round(leaflet_y, 7), round(leaflet_x, 7)]

def map_blueprint_to_gps(camera_id, bp_y, bp_x):
    src = np.array([[[bp_x, bp_y]]], dtype=np.float32)
    H = np.array([
        [-0.038804159027604763, -0.0688000635773231, 78.54045303882491],
        [-0.008519601801808484, -0.015105329658011889, 17.243868435303906],
        [-0.000494065752930481, -0.0008759831020979834, 1.0]
    ], dtype=np.float32)
    dst = cv2.perspectiveTransform(src, H)
    lng = float(dst[0][0][0])
    lat = float(dst[0][0][1])
    return [round(lat, 7), round(lng, 7)]