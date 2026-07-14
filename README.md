# t-map: Real-Time Facility Monitoring & AI Safety Tracker

`t-map` is a production-grade, security-orchestrated facility monitoring application built for industrial desktop web environments. It features live multi-camera RTSP/video streaming, real-time computer vision (YOLOv8 people counting & worker tracking), and asynchronous Vision-Language Models (VLM) for automatic situation analysis mapped on an interactive blueprint dashboard.

---

## 🏗️ Repository Layout
Ensure the following directories exist when working on the project. Note that folders containing heavy binary files (`models/`, `test_video/`, `evidence/`) and dependencies are ignored by Git to keep the repository lightweight.

```
t-map/
├── backend/                  # Fast API application
│   ├── ai/                   # AI Tracking, Calibration, and VLM integration
│   │   ├── modules/          # Fall detection, crowd anomalies, zone intrusion
│   │   └── bytetrack.yaml    # Custom tracker thresholds configuration
│   ├── api/                  # Routes and API endpoints
│   ├── core/                 # Database initialization, App routing, Global state
│   ├── data/                 # JSON registries, CSV logs, SQLite DB (WAL format)
│   └── workers/              # Decoupled mathematical rules event queue
├── mediamtx/                 # MediaMTX RTSP stream server folder
│   ├── mediamtx.exe          # MediaMTX executable
│   └── mediamtx.yml          # MediaMTX configurations
├── models/                   # [IGNORED] Stores local PyTorch and TensorRT models
├── test_video/               # [IGNORED] Stores local fallback demo MP4 files
├── evidence/                 # [IGNORED] Stores screenshots captured during critical events
├── public/                   # Static assets for React frontend
├── src/                      # React frontend source files
├── docker-compose.yml        # Orchestrates Redis and PostgreSQL database
├── server.py                 # FastAPI runner script
└── requirements.txt          # Backend dependencies
```

---

## 🛠️ Technology Stack

### Backend & AI Pipelines
- **FastAPI / Uvicorn**: High-performance asynchronous API server.
- **Celery & Redis**: Decoupled asynchronous worker queue for CPU/GPU heavy VLM analysis.
- **PostgreSQL / SQLite**: Dual-mode storage registry (SQLite with WAL enabled for local setup, Postgres for centralized database setups).
- **Ultralytics YOLOv8**: Real-time object detection and tracking.
- **Ollama**: Local container-based Vision-Language Model execution.

### Frontend
- **React (Vite)**: Highly responsive single page application.
- **Leaflet & React-Leaflet**: Fully customized 2D blueprint coordinate system matching real-world GPS coordinates via homography projection.

---

## 🖥️ AI Models Guide (CRITICAL)

To run the application's AI modules and safety tracking, you must set up the local models manually.

### 1. YOLOv8 Tracking Models
Place the models inside the `models/` directory in the project root:
- `yolov8l.pt`: PyTorch checkpoint. Used as a baseline fallback.
- `yolov8m.engine`: TensorRT optimized engine (Medium size). Recommended for production GPU environments for balanced FPS/accuracy.
- `yolov8l.engine`: TensorRT optimized engine (Large size). Highest accuracy tracking.

### 2. Ollama Vision-Language Models (VLM)
Ensure **Ollama** is installed and running on your machine. Run the following terminal commands to pull the necessary models:
```bash
# General triage model (fast, checking initial parameters)
ollama pull llava:latest

# Heavy reasoning/visual logic model (detailed posture/threat analysis)
ollama pull qwen2.5vl:3b
```

---

## 🚀 Step-by-Step Running Instructions

### 1. Backend Setup
1. Create and activate a virtual environment in the `backend/` folder:
   ```bash
   python -m venv backend/gpu_env
   
   # Windows (PowerShell):
   .\backend\gpu_env\Scripts\Activate.ps1
   
   # Linux / macOS:
   source backend/gpu_env/bin/activate
   ```
2. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Start Message Broker & DB Services (Docker)
Start central Redis & central TimescaleDB databases in detached mode:
```bash
docker-compose up -d
```

### 3. Start MediaMTX RTSP Server
Navigate into the `mediamtx` folder and run the RTSP stream publisher:
```bash
# Windows
cd mediamtx
.\mediamtx.exe

# Linux / macOS
cd mediamtx
./mediamtx
```

### 4. Run Celery Workers
Start Celery to handle async AI VLM prompts queue:
```bash
# Windows / Linux / macOS (Ensure venv is active)
celery -A backend.tasks worker --loglevel=info --concurrency=2
```

### 5. Run the Backend API Server
Launch the FastAPI server:
```bash
python server.py
```
- API starts at: `http://localhost:5000`
- Swagger UI Documentation: `http://localhost:5000/docs`

### 6. Frontend Setup & Run
Open a separate terminal window and run:
```bash
npm install
npm run dev
```
- Frontend starts at: `http://localhost:5173`

---

## 💾 GitHub Setup & Push Guidelines

Because `models/`, `test_video/`, and `evidence/` are ignored by `.gitignore` to prevent committing massive files (GBs), configure your repository and push to GitHub using the following commands:

1. Initialize git locally (if not already done):
   ```bash
   git init
   ```
2. Link your local directory to your GitHub repository:
   ```bash
   git remote add origin https://github.com/Vaishnav315/T-map.git
   ```
3. Stage and commit all important files (configs, source code, server scripts):
   ```bash
   git add .
   git commit -m "Initial commit: Production-grade facility monitoring with async live streams and worker tracking"
   ```
4. Rename branch to `main` and push:
   ```bash
   git branch -M main
   git push -u origin main
   ```
*(Note: Ensure you do NOT force-add ignored files to keep the remote repository small and clean!)*
