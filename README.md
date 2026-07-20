# 🛡️ SentinelIQ — Enterprise AI Safety Platform

> **Industrial-grade AI safety monitoring as a multi-tenant SaaS.**
> Multi-camera RTSP ingestion, dynamic VRAM load-balancing, YOLOv8 + ByteTrack tracking, 2D blueprint homography projection, and VLM alert verification.

---

## ⚡ Quick Start (Development Mode)

### Prerequisites
- Python 3.11+
- Node.js 18+

### 1. Install Dependencies

```bash
# Backend
pip install -r requirements.txt

# Frontend
npm install
```

### 2. Configure Environment

```bash
cp .env.example .env
# Ensure SECRET_KEY is set.
```

### 3. Run Backend Server

```bash
# Start the FastAPI engine (Port 5001 to avoid macOS AirPlay conflicts)
uvicorn backend.core.app:app --host 0.0.0.0 --port 5001 --reload

# API: http://localhost:5001
# Docs: http://localhost:5001/api/docs
```

### 4. Run Frontend

```bash
npm run dev
# App: http://localhost:5173
```

---

## 🏢 SaaS Multi-Tenancy

SentinelIQ is built for scale, supporting multi-organization SaaS deployments.
Each organization (Tenant) has an isolated environment for cameras, users, and billing plans.

- **Role-Based Access (RBAC):** `admin` | `safety_manager` | `viewer`
- **Plan Limits:** Starter (10 cameras) | Professional (50 cameras) | Enterprise (Unlimited)
- **Data Isolation:** All queries filter by `tenant_id` at the database layer.

---

## 📷 Camera Integrations

Connect cameras via the **Settings -> Integrations** tab:
1. **Bulk RTSP Import** — Paste JSON arrays of RTSP URLs.
2. **ONVIF Auto-Discovery** — Scan local subnets for compatible IP cameras.
3. **VMS Database Connect** — Sync directly with external PostgreSQL/MySQL databases (Milestone, Genetec, etc.).

---

## 🌐 Webhooks & API Keys

Push real-time safety alerts to your external systems (ERP, HSE dashboards, Slack).
- **Webhooks:** Configure endpoint URLs with HMAC signing secrets to receive live POST requests on threat detection.
- **API Keys:** Generate secure `sk-...` bearer tokens for external script access.

---

## 🚀 Architecture Overview

```text
SentinelIQ Platform
├── Frontend (React + Vite + Leaflet)
│   ├── Unified Dashboard  — Live Map, Heatmaps, System Status
│   ├── Settings           — SaaS Tenant Mgmt, Integrations, Webhooks
│   └── Analytics          — VLM Alert Verification Center
│
├── Backend (FastAPI)
│   ├── saas_routes.py        — Organizations & billing limits
│   ├── integration_routes.py — ONVIF/RTSP discovery
│   └── webhooks.py           — HMAC signed async dispatch
│
└── Adaptive AI Pipeline (gpu_manager.py)
    ├── GPU Load Balancer     — Auto-shifts load between multiple GPUs
    ├── YOLOv8 / ByteTrack    — Real-time bounding box tracking
    ├── Homography Mapper     — 2D Perspective Projection
    └── VLM Integrations      — Llava/Qwen threat verification
```

---

## 🛠️ Security

| Feature | Status |
|---|---|
| JWT Authentication | ✅ |
| Role-Based Access Control | ✅ |
| Multi-tenant Isolation | ✅ |
| API Key Hashing (SHA-256) | ✅ |
| Webhook HMAC Signatures | ✅ |

---

**SentinelIQ** — Built for zero false-alarms and maximum factory safety.
