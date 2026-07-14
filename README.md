# t-map: Real-Time Facility Monitoring (Desktop Application)

`t-map` is a production-ready, security-orchestrated facility monitoring application designed for desktop web environments. It integrates live RTSP video streaming, real-time computer vision (YOLOv8 people counting & worker tracking), and advanced Vision-Language Models (VLM) for situation analysis on a React-Leaflet interactive map.

---

## Senior Developer Hand-Off Notes

This repository contains the **Desktop UI** and the **Core Backend Service**. 
- The mobile UI has been extracted to a separate repository/app (`ai-security-monitor` / `tasl_sentinel`).
- The components in `src/pages/` have been refactored and cleaned up (e.g., `DashboardDesktop.jsx`, `DashboardMobile.jsx`) to clearly distinguish responsive behaviors while keeping the primary desktop experience intact.

## Key Features

- **Interactive Live Map**: Interactive blue-print mapping with Leaflet, overlaying camera views, live statuses, and worker tracks.
- **Asynchronous AI Inference**: Decoupled task queue powered by Celery and Redis to handle concurrent object detection and VLM prompts without crashing the main application server.
- **Real-Time Video Feeds**: Low-latency video streaming integrated with MediaMTX.
- **Operator Authentication**: Secure signup/login using JSON Web Tokens (JWT) and encrypted user credentials (bcrypt).
- **Comprehensive Logging**: Auditable registers for system events, AI/VLM warning alerts, and gate ingress/egress events.

---

## Tech Stack

### Frontend
- **Framework**: React (Vite)
- **Mapping**: Leaflet / React-Leaflet
- **Styling**: Vanilla CSS (Industrial Dark/Light System)

### Backend
- **Web Framework**: FastAPI (Uvicorn)
- **Task Queue**: Celery
- **Message Broker**: Redis
- **Database**: SQLite (SQLAlchemy)

### AI & Machine Learning
- **Object Detection**: Ultralytics YOLOv8 (PyTorch)
- **Vision-Language Model**: Ollama (Llava/VLM models)
- **Computer Vision**: OpenCV, NumPy, Homography matrix calculations

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10+
- Node.js & npm
- Docker (for Redis and Postgres database)
- [Ollama](https://ollama.com/) (installed locally for VLM inference)

### 2. Environment Setup

#### Clone the Repository
```bash
git clone <repository-url>
cd t-map
```

#### Backend Setup
We recommend using a virtual environment (e.g., `gpu_env`):
```bash
# Create and activate environment
python -m venv backend/gpu_env
# Windows:
.\backend\gpu_env\Scripts\activate
# Linux/macOS:
source backend/gpu_env/bin/activate

# Install requirements
pip install -r requirements.txt
```

#### Frontend Setup
```bash
npm install
```

### 3. Running the Services

#### Step 1: Start Redis (Broker & Result Backend)
Ensure Docker is running, then start the Redis service:
```bash
docker-compose up -d redis
```

#### Step 2: Start the Celery Worker
Activate your virtual environment and start the worker to handle AI task requests asynchronously:
```bash
celery -A backend.tasks worker --loglevel=info --concurrency=2
```

#### Step 3: Run FastAPI Application
Start the backend server:
```bash
python server.py
```
The server will start at `http://localhost:5000`. You can inspect the interactive OpenAPI/Swagger docs at `http://localhost:5000/docs`.

#### Step 4: Run React Frontend
Start the Vite development server:
```bash
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Deployment & Production Notes

- **Celery Concurrency**: To run YOLO & VLM inferences on GPU environments, restrict Celery concurrency (`--concurrency=1` or `2`) inside the container configurations to avoid VRAM congestion.
- **Production builds**:
  - Frontend: `npm run build` compiles static assets to the `dist/` directory.
  - Backend: Run Uvicorn without reload flag: `uvicorn backend.core.app:app --host 0.0.0.0 --port 5000`.
