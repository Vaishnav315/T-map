import torch
import psutil
import logging
from typing import Dict, List, Optional
import threading

logger = logging.getLogger(__name__)

class GPUManager:
    """
    SentinelIQ Adaptive GPU Load Balancer.
    Detects available hardware (CUDA/MPS/CPU), monitors VRAM and system memory,
    and intelligently assigns camera streams to the least-loaded device.
    """
    def __init__(self):
        self.lock = threading.Lock()
        
        # Determine available hardware
        self.has_cuda = torch.cuda.is_available()
        self.has_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        
        self.devices: Dict[str, dict] = {}
        self.camera_assignments: Dict[str, str] = {}  # camera_id -> device_id
        
        self._initialize_devices()

    def _initialize_devices(self):
        with self.lock:
            if self.has_cuda:
                num_gpus = torch.cuda.device_count()
                for i in range(num_gpus):
                    props = torch.cuda.get_device_properties(i)
                    self.devices[f"cuda:{i}"] = {
                        "type": "cuda",
                        "index": i,
                        "name": props.name,
                        "total_vram_mb": props.total_memory / (1024 ** 2),
                        "compute_capability": float(f"{props.major}.{props.minor}"),
                        "assigned_cameras": 0
                    }
                logger.info(f"[GPUManager] Discovered {num_gpus} CUDA GPUs.")
            
            elif self.has_mps:
                # Apple Silicon
                self.devices["mps"] = {
                    "type": "mps",
                    "index": 0,
                    "name": "Apple Silicon (MPS)",
                    "total_vram_mb": psutil.virtual_memory().total / (1024 ** 2), # Shared memory
                    "assigned_cameras": 0
                }
                logger.info("[GPUManager] Discovered Apple Silicon (MPS).")
                
            else:
                # CPU Fallback
                self.devices["cpu"] = {
                    "type": "cpu",
                    "index": 0,
                    "name": "CPU",
                    "total_vram_mb": psutil.virtual_memory().total / (1024 ** 2),
                    "assigned_cameras": 0
                }
                logger.info("[GPUManager] No GPU found. Falling back to CPU.")

    def get_device_stats(self) -> dict:
        """Returns current utilization for logging / API."""
        stats = {}
        for dev_id, info in self.devices.items():
            if info["type"] == "cuda":
                free, total = torch.cuda.mem_get_info(info["index"])
                free_mb = free / (1024 ** 2)
                used_mb = info["total_vram_mb"] - free_mb
                utilization = (used_mb / info["total_vram_mb"]) * 100
            elif info["type"] in ["mps", "cpu"]:
                mem = psutil.virtual_memory()
                used_mb = mem.used / (1024 ** 2)
                utilization = mem.percent
            
            stats[dev_id] = {
                "name": info["name"],
                "assigned_cameras": info["assigned_cameras"],
                "memory_used_percent": round(utilization, 1)
            }
        return stats

    def assign_camera(self, camera_id: str) -> str:
        """
        Assigns a camera to the least loaded device.
        """
        with self.lock:
            # If already assigned, return it
            if camera_id in self.camera_assignments:
                return self.camera_assignments[camera_id]

            # Find best device based on fewest assigned cameras
            # (In a real massive deployment, we'd weight this by available VRAM)
            best_device = min(self.devices.keys(), key=lambda d: self.devices[d]["assigned_cameras"])
            
            self.devices[best_device]["assigned_cameras"] += 1
            self.camera_assignments[camera_id] = best_device
            
            logger.info(f"[GPUManager] Assigned camera {camera_id} to {best_device}")
            return best_device

    def release_camera(self, camera_id: str):
        """Releases a camera assignment."""
        with self.lock:
            if camera_id in self.camera_assignments:
                dev_id = self.camera_assignments[camera_id]
                self.devices[dev_id]["assigned_cameras"] -= 1
                del self.camera_assignments[camera_id]
                logger.info(f"[GPUManager] Released camera {camera_id} from {dev_id}")

# Global singleton
gpu_manager = GPUManager()
