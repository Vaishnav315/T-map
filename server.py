#!/usr/bin/env python3
"""
TASL Sentinel — Server Entry Point
===================================
Run this file from the project root to start the backend:

    python server.py

"""

import sys
import os
import uvicorn

# Add backend directory to Python path
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_path)

if __name__ == '__main__':
    print("=" * 50)
    print("  TASL Sentinel Backend Server (FastAPI)")
    print("  Swagger UI: http://localhost:5000/docs")
    print("=" * 50)
    
    uvicorn.run(
        "backend.core.app:app",
        host="0.0.0.0",
        port=5000,
        reload=False,           # CRITICAL: reload=True kills video threads on every file save
        workers=1,              # Single process — threads share the GPU and frame buffers
        timeout_keep_alive=75,  # Keep HTTP connections alive longer for streaming
        loop="asyncio",
    )
