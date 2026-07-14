import os
import time
from celery import Celery
import logging

logger = logging.getLogger(__name__)

# Initialize Celery app
# In production, use the Redis service defined in docker-compose
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True
)

@celery_app.task(bind=True, name="backend.tasks.run_yolo_inference")
def run_yolo_inference(self, image_data_base64: str, confidence_threshold: float = 0.5):
    """
    Simulated asynchronous YOLO inference task.
    In a real scenario, you'd decode the base64 image, pass it to Ultralytics YOLO,
    and return the bounding box coordinates.
    """
    try:
        logger.info(f"Task {self.request.id}: Starting YOLO inference...")
        # Simulate inference time (1-3 seconds based on typical GPU loads)
        time.sleep(2)
        
        # Simulated result structure
        result = {
            "status": "success",
            "model": "yolov8n",
            "detections": [
                {"class": "person", "confidence": 0.89, "bbox": [100, 150, 300, 450]},
                {"class": "person", "confidence": 0.75, "bbox": [320, 180, 500, 420]}
            ],
            "count": 2
        }
        logger.info(f"Task {self.request.id}: YOLO inference completed.")
        return result
    except Exception as e:
        logger.error(f"Task {self.request.id} failed: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task(bind=True, name="backend.tasks.run_vlm_prompt")
def run_vlm_prompt(self, image_data_base64: str, prompt: str):
    """
    Simulated asynchronous Ollama VLM prompt execution.
    """
    try:
        logger.info(f"Task {self.request.id}: Starting VLM inference with prompt: {prompt}")
        # Simulate VLM inference time
        time.sleep(4)
        
        # Simulated result
        result = {
            "status": "success",
            "model": "llava",
            "prompt": prompt,
            "response": "Based on the image, I can see two workers in the warehouse handling packages safely."
        }
        logger.info(f"Task {self.request.id}: VLM inference completed.")
        return result
    except Exception as e:
        logger.error(f"Task {self.request.id} failed: {e}")
        return {"status": "error", "message": str(e)}
