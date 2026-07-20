# 🛡️ SentinelIQ — System Architecture Report

## 1. Executive Summary
**SentinelIQ** is a production-grade, multi-tenant AI safety monitoring SaaS platform designed for industrial environments (factories, logistics hubs, chemical plants). 

Unlike traditional passive CCTV VMS (Video Management Systems), SentinelIQ utilizes a decoupled, asynchronous, multimodal AI pipeline. It ingests high-frequency RTSP streams, performs real-time YOLOv8 bounding-box detection, maps pixel coordinates into 2D blueprint space via homography perspective projection, and verifies complex visual threats using a dynamic VLM (Vision-Language Model) cascade.

## 2. Core Subsystems

### 2.1 Web Layer & Multi-Tenancy (FastAPI + React)
- **Multi-Tenant Data Isolation**: The system is designed for B2B SaaS deployment. All core entities (`users`, `camera_integrations`, `webhooks`, `system_logs`) are isolated by a `tenant_id`. 
- **Role-Based Access Control (RBAC)**: Users are assigned roles (`admin`, `safety_manager`, `viewer`) determining access to configuration and billing.
- **Frontend Dashboard**: A React/Vite unified responsive dashboard incorporating real-time websockets, Leaflet blueprint mapping, and comprehensive data analytics (heatmaps, compliance scores).

### 2.2 Integrations & Webhooks
- **Camera Auto-Discovery**: Support for bulk RTSP import, ONVIF subnet scanning, and external VMS database syncing.
- **Webhook Dispatcher**: External systems (Slack, ERP, HSE software) can receive real-time, HMAC-signed JSON payloads immediately upon verified threat detection.

### 2.3 Adaptive AI Engine & GPU Load Balancing
- **`gpu_manager.py`**: Monitors system VRAM and dynamically allocates AI models. It shifts processing load based on available GPU capacity (NVIDIA CUDA, Apple Metal/MPS, or CPU fallback).
- **Sub-second Latency RTSP Ingestion**: Uses `grab()` frame-skipping over OpenCV to discard backlog buffer frames, ensuring AI processing always receives the most recent "live" frame.

## 3. The "Diamond Cascade" AI Pipeline
To prevent GPU exhaustion while maintaining high accuracy, SentinelIQ avoids sending every camera frame to heavy VLMs. Instead, it utilizes a multi-tier filtering funnel:

1. **Deterministic Event Trigger (YOLOv8 + ByteTrack)**: Mathematical rules (aspect ratio changes for falls, stationary timers > 15s for idle workers, polygon overlap for zone intrusion) trigger a candidate event.
2. **IVF (Inference Value Function) Filter**: Calculates structural visual entropy differences on target crops. Drops frames if visually identical to recent processing.
3. **Tier 1: Llava Triage Model (Fast VQA)**: Executes fast VQA screening (~300ms).
   - Score < 50: False alarm, suppressed.
   - Score >= 85: Blatant threat, directly alerts.
4. **Tier 2: Qwen 2.5-VL 3B (Heavy Reasoning)**: Handles ambiguous scenes (score 50–84) for structured JSON verification.

## 4. Homography & Cross-Camera Tracking
- **Perspective Matrix**: Maps 2D camera pixels to 2D blueprint (Leaflet) coordinates using `cv2.getPerspectiveTransform`.
- **Spatial Dead-Reckoning Re-ID**: Instead of unreliable clothing-color matching (which fails with identical factory uniforms), SentinelIQ predicts worker movement vectors across camera boundaries, achieving seamless track ID transfer across the facility.

## 5. Storage & Persistence
- **Dual-Mode Persistence**: SQLite (with WAL) for zero-config edge hardware deployment; PostgreSQL fallback for centralized enterprise SaaS deployments.
- **AES-256 Config Vault**: RTSP credentials and sensitive variables are encrypted, allowing safe version control of configurations.
