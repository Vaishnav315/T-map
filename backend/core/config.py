# ============================================
# TASL Sentinel — Camera Configuration
# ============================================
# Central configuration for all camera hardware addresses, 
# credentials, and coordinate mappings for the plant floor plan.
#
# To add a new camera, duplicate an entry and update the values.
# The 'coords' field maps to the Leaflet CRS.Simple [y, x] position.
# ============================================

# Check for optional dependencies once at startup
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


# Strict MediaMTX Proxy Registry
CAMERA_REGISTRY = {
    "224": {"id": "224", "name": "Cam 224 (Main Gate)"},
    "225": {"id": "225", "name": "Cam 225 (Assembly Line A)"},
    "226": {"id": "226", "name": "Cam 226 (Storage North)"},
    "227": {"id": "227", "name": "Cam 227 (Exit Gate)"},
    "228": {"id": "228", "name": "Cam 228 (Tasl Unit-1 Entrance)"},
    "3": {"id": "3", "name": "Cam 3"},
    "4": {"id": "4", "name": "Cam 4"},
    "8": {"id": "8", "name": "Cam 8"},
    "9": {"id": "9", "name": "Cam 9"},
    "10": {"id": "10", "name": "Cam 10"}, 
    "11": {"id": "11", "name": "Cam 11"}
}