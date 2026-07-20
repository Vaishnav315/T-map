import cv2
import numpy as np

# 1. Define the blueprint asset image height from your App.jsx configuration
BLUEPRINT_HEIGHT = 1290

# 2. Input your exact MS Paint coordinates
# Index 0: Front-Left | Index 1: Back-Right | Index 2: Back-Left | Index 3: Front-Right
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

# 3. Compute the Homography Matrix
H = cv2.getPerspectiveTransform(pts_video, pts_map_paint)

print("═" * 60)
print(" MATRIX PIPELINE INITIALIZED SUCCESSFULLY")
print("═" * 60)

def convert_video_to_leaflet(video_x, video_y):
    """
    Transforms a single point from the camera stream perspective 
    into the exact [Y, X] coordinate array format required by React-Leaflet.
    """
    # Reshape the source coordinate to fit OpenCV's matrix math requirements
    src_point = np.array([[[video_x, video_y]]], dtype=np.float32)
    
    # Run the perspective transformation matrix multiplication
    transformed = cv2.perspectiveTransform(src_point, H)
    map_x = transformed[0][0][0]
    map_y = transformed[0][0][1]
    
    # Invert the Y-axis to convert from MS Paint space to Leaflet space
    leaflet_x = round(map_x, 2)
    leaflet_y = round(BLUEPRINT_HEIGHT - map_y, 2)
    
    # Return in Leaflet's native [Lat, Lng] layout style which is [Y, X]
    return [leaflet_y, leaflet_x]

# ══════════════════════════════════════════════════════════════════
#  FORCE TEST EXECUTION
# ══════════════════════════════════════════════════════════════════
# Mock detection point: simulating a person's feet tracked at video pixel (400, 200)
test_video_x = 400
test_video_y = 200

leaflet_coords = convert_video_to_leaflet(test_video_x, test_video_y)

print(f"Target Input (YOLO Video Bounding Box Base): X={test_video_x}, Y={test_video_y}")
print("-" * 60)
print(f"Matrix Output Array for your App.jsx map marker:")
print(f" 👉 {leaflet_coords}")
print("-" * 60)
print("If you paste that output array directly into your React map as a marker position,")
print("the marker will appear exactly where that person is standing on the factory floor!")
print("═" * 60)