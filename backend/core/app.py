import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in Python path for relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.api.routes import api_router

def create_app() -> FastAPI:
    """Factory function to create and configure the FastAPI app."""
    app = FastAPI(
        title="TASL Sentinel API",
        description="FastAPI Backend with Celery Task Queue",
        version="2.0.0"
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register API routes
    app.include_router(api_router)
    
    # Startup hooks
    @app.on_event("startup")
    def startup_event():
        from backend.core.state import start_state_updater, initialize_state
        from backend.core.config_loader import loader
        try:
            registry = loader.get_camera_registry()
            initialize_state(registry)
            start_state_updater()
            print("[FASTAPI STARTUP] Camera state initialized and VLM background worker thread started.")
        except Exception as e:
            print(f"[FASTAPI STARTUP ERROR] Failed to run startup hooks: {e}")
            
    return app

app = create_app()
