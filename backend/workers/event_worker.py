import threading
import queue
import time
from backend.core import database
from backend.core import state

# Decoupled Event Bus Queue
event_bus = queue.Queue(maxsize=1000)

def submit_event_task(engine, frame_data, raw_frame, tracked_positions):
    """Producer function: Injects tracker data into the event engine bus asynchronously."""
    try:
        event_bus.put_nowait((engine, frame_data, raw_frame, tracked_positions))
    except queue.Full:
        print("[EVENT BUS] Warning: Event Engine is bottlenecked. Dropping rules evaluation frame.")

def event_worker_daemon():
    """Consumer Daemon: Pulls tracks off the bus and executes heavy mathematical rules independently."""
    print("[EVENT ENGINE] Asynchronous Event Rules Worker Daemon started.")
    while True:
        try:
            task = event_bus.get()
            if task is None:
                continue
            
            engine, frame_data, raw_frame, tracked_positions = task
            camera_id = engine.camera_id
            
            # Run the heavy math rules (Fall, Crowd, Idle, Zone)
            crossed_events = engine.event_manager.update(frame_data, raw_frame)
            
            # Sync local counts
            engine.gate_in_count = engine.event_manager.in_count
            engine.gate_out_count = engine.event_manager.out_count
            
            if str(camera_id) == "3" and engine.gate_counting and crossed_events:
                # Map local tids to their physical global_ids assigned by PositionReIDRegistry
                tid_to_gid = {tp["tid"]: tp.get("global_id") for tp in tracked_positions if not tp.get("is_ghost")}
                
                with state.state_lock:
                    if 'counted_global_ids' not in state.shared_stats:
                        state.shared_stats['counted_global_ids'] = set()
                        
                    for direction, tid in crossed_events:
                        gid = tid_to_gid.get(tid)
                        
                        # Use global_id to prevent double-counting across overlapping cameras (Cam 3 & 4)
                        if gid is not None:
                            dedup_key = f"{gid}_{direction}"
                            if dedup_key in state.shared_stats['counted_global_ids']:
                                continue  # Already counted this person across the gate
                            state.shared_stats['counted_global_ids'].add(dedup_key)
                            
                        # Standard counting
                        if direction == "IN":
                            state.shared_stats['global_gate_in'] = state.shared_stats.get('global_gate_in', 0) + 1
                            database.insert_gate_event("IN", 0.0, 0.0)
                        elif direction == "OUT":
                            state.shared_stats['global_gate_out'] = state.shared_stats.get('global_gate_out', 0) + 1
                            database.insert_gate_event("OUT", 0.0, 0.0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[EVENT ENGINE WORKER ERROR] {e}")

# Automatically start the event worker thread when this module is loaded
threading.Thread(target=event_worker_daemon, daemon=True).start()
