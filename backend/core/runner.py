import sys
import os
import time
import threading
import asyncio

# Resolve paths
backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from backend.stream.streamer import toggle_background_tracking, _active_engines
from backend.core.config_loader import loader
from backend.ai.vlm_integration import vlm_loop

def initialize_orchestration():
    """Orchestration initialization routine registering up to 50 camera streams into the producer pool."""
    print("=" * 60)
    print("   TASL Sentinel Global Orchestration Pipeline Runner")
    print("=" * 60)
    
    # Retrieve camera registry configurations
    registry = loader.get_camera_registry()
    camera_ids = list(registry.keys())
    
    # Target exactly 50 streams as requested by specification
    target_count = 50
    registered = 0
    
    for cam_id in camera_ids:
        if registered >= target_count:
            break
            
        cam_details = registry[cam_id]
        cam_name = cam_details.get("Name", f"Cam {cam_id}")
        
        # We start the stream engine and enable background tracking
        # This spawns the lightweight producer thread pulling from MediaMTX at 1 FPS
        try:
            toggle_background_tracking(cam_id, enable=True)
            registered += 1
            print(f"[ORCHESTRATION] Registered stream {registered}/{target_count}: ID {cam_id} ({cam_name})")
        except Exception as e:
            print(f"[ORCHESTRATION ERROR] Failed to register camera {cam_id}: {e}")
            
    print(f"\n[ORCHESTRATION COMPLETE] {registered} camera channels registered into the multiplexer architecture.")
    print("=" * 60)

if __name__ == "__main__":
    # Standard entry point to test run the pipeline orchestration standalone
    initialize_orchestration()
    
    try:
        # Keep main thread alive to allow producers and background batch workers to run
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ORCHESTRATION] Standalone loop terminated by user. Shutting down...")
