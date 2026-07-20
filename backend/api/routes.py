"""
SentinelIQ AI Safety Platform — Core API Routes
==========================================
Production-hardened: env-driven secrets, RBAC middleware,
rate limiting on auth, authenticated evidence serving, and
deprecation fixes (datetime.now(timezone.utc)).
"""

import time
import os
import json
import secrets
import threading
from collections import defaultdict
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Response, HTTPException, status, Depends
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, field_validator
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from backend.core import state
from backend.core import database
from backend.core.config_loader import loader
from backend.stream.streamer import (
    get_video_stream_async, toggle_background_tracking,
    process_video_click,
)
from backend.tasks import run_yolo_inference, run_vlm_prompt
from celery.result import AsyncResult

api_router = APIRouter(tags=["Core"])

# ── Constants ────────────────────────────────────────────────────────────────
EVIDENCE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "evidence")
)
os.makedirs(EVIDENCE_DIR, exist_ok=True)

ACTIVE_TOKENS: dict = {}
INTERNAL_YOLO_USER = "sentineliq_yolo_internal"

# ── Security Config (all from environment) ───────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "")
INTERNAL_YOLO_SECRET = os.getenv("INTERNAL_YOLO_SECRET", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


# ── Rate Limiter (simple in-memory, per IP) ──────────────────────────────────
_login_attempts: dict = defaultdict(list)
_rl_lock = threading.Lock()
LOGIN_MAX_ATTEMPTS = 10       # max attempts per window
LOGIN_WINDOW_SECONDS = 300    # 5 minute window


def _check_rate_limit(ip: str):
    """Raises 429 if IP has exceeded login attempt limit."""
    now = time.time()
    with _rl_lock:
        attempts = _login_attempts[ip]
        # Prune old entries outside window
        _login_attempts[ip] = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        if len(_login_attempts[ip]) >= LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many login attempts. Try again in {LOGIN_WINDOW_SECONDS // 60} minutes.",
            )
        _login_attempts[ip].append(now)


# ── JWT Helpers ──────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=15)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode and validate JWT; return the user record."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = database.get_user(username)
    if user is None:
        raise credentials_exception
    return user


def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory for role-based access control.
    Usage: Depends(require_role("admin", "safety_manager"))
    """
    async def _check(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role", "viewer")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(allowed_roles)}. Your role: {user_role}",
            )
        return current_user
    return _check


# ── Auth Endpoints ───────────────────────────────────────────────────────────
class SignupModel(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (underscores/hyphens allowed).")
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be between 3 and 50 characters.")
        return v.lower().strip()


@api_router.post("/api/signup", summary="Register a new operator account")
def signup(user: SignupModel):
    success = database.create_user(user.username, user.email, user.password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists.",
        )
    return {"message": "Account created successfully. Please sign in."}


@api_router.post("/api/login", summary="Authenticate and receive JWT token")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    # Rate limit by client IP
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    user = database.get_user(form_data.username)
    if not user or not database.verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user["username"], "role": user.get("role", "viewer")},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "username": user["username"],
            "email": user["email"],
            "role": user.get("role", "viewer"),
        },
    }


@api_router.get("/api/me", summary="Get current authenticated user details")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user.get("role", "viewer"),
        "tenant_id": current_user.get("tenant_id", "default"),
    }


# ── Stats & Logs ─────────────────────────────────────────────────────────────
@api_router.get("/api/stats", summary="Live system statistics")
def get_stats(current_user: dict = Depends(get_current_user)):
    from backend.ai.gpu_manager import gpu_manager
    with state.state_lock:
        stats = state.shared_stats.copy()
        stats["unread_alerts"] = state._unread_alert_count
        try:
            daily_counts = database.get_daily_gate_counts()
            stats["global_gate_in"] = daily_counts.get("IN", 0)
            stats["global_gate_out"] = daily_counts.get("OUT", 0)
        except Exception as e:
            pass
            
        # Append GPU load balancing stats
        stats["gpu_load"] = gpu_manager.get_device_stats()
            
        return stats


@api_router.get("/api/logs", summary="Recent system logs")
def get_logs(current_user: dict = Depends(get_current_user)):
    return database.get_recent_system_logs()


@api_router.get("/api/gate_events", summary="Recent gate events")
def get_gate_events(current_user: dict = Depends(get_current_user)):
    return database.get_recent_gate_events()


@api_router.get("/api/alert_logs", summary="Recent alert logs")
def get_alert_logs(current_user: dict = Depends(get_current_user)):
    return database.get_recent_alert_logs()

@api_router.get("/api/telemetry", summary="Recent position telemetry data for heatmap/analytics")
def get_position_telemetry(hours: int = 24, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "default") if current_user else "default"
    return database.get_position_telemetry(hours=hours, tenant_id=tenant_id)


@api_router.get("/api/vlm_logs", summary="Recent VLM inference logs")
def get_vlm_logs(current_user: dict = Depends(get_current_user)):
    return database.get_recent_vlm_logs()


@api_router.post("/api/alerts/mark_read", summary="Mark all alerts as read")
def mark_alerts_read(current_user: dict = Depends(get_current_user)):
    state.reset_unread_count()
    return {"success": True}


# ── Evidence Files (authenticated) ───────────────────────────────────────────
@api_router.get("/evidence/{filename}", summary="Serve alert evidence screenshot")
def serve_evidence(filename: str, current_user: dict = Depends(get_current_user)):
    """Evidence files are protected — only authenticated users can access screenshots."""
    # Sanitize filename to prevent path traversal
    safe_name = os.path.basename(filename)
    file_path = os.path.join(EVIDENCE_DIR, safe_name)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found.")
    return FileResponse(file_path)


# ── Camera Config ─────────────────────────────────────────────────────────────
@api_router.get("/api/config/cameras", summary="Get all camera configurations")
def get_cameras_config(current_user: dict = Depends(get_current_user)):
    registry = loader.get_camera_registry()
    layouts = loader.get_map_layout()

    real_coords = {
        "28": [17.2439174, 78.5403015],
        "27": [17.2438281, 78.5407760],
        "33": [17.2439568, 78.5405590],
        "35": [17.2440603, 78.5414556],
        "3":  [17.2444810, 78.5418086],
    }

    merged_cameras = []
    for cam_id, info in registry.items():
        layout = layouts.get(cam_id)
        px = layout.get("Percentage_X") if layout else None
        py = layout.get("Percentage_Y") if layout else None
        viewing_angle = layout.get("Viewing_Angle", 0) if layout else 0

        blueprint_coords = (
            [round((py / 100.0) * 1290.0, 2), round((px / 100.0) * 2048.0, 2)]
            if px is not None and py is not None else None
        )
        coords = real_coords.get(cam_id)
        accessible = cam_id not in ["145", "102", "105"]

        merged_cameras.append({
            "id": cam_id,
            "name": info.get("Name", f"Camera {cam_id}"),
            "ip": info.get("IP", "127.0.0.1"),
            "brand": info.get("Brand", "Generic"),
            "area": info.get("Allocation", "General"),
            "coords": coords,
            "blueprint_coords": blueprint_coords,
            "percentage_x": px,
            "percentage_y": py,
            "viewing_angle": viewing_angle,
            "accessible": accessible,
            "status": "ONLINE" if accessible else "OFFLINE",
        })
    return merged_cameras


# ── Stream Token ──────────────────────────────────────────────────────────────
@api_router.get("/api/stream_token/{camera_id}", summary="Get a one-time RTSP stream token")
def get_stream_token(camera_id: str, current_user: dict = Depends(get_current_user)):
    token = secrets.token_hex(16)
    ACTIVE_TOKENS[token] = {
        "camera_id": camera_id,
        "expires_at": time.time() + 60.0,
    }
    return {"success": True, "token": token, "path": f"live/stream_{camera_id}"}


# ── Video Feed ────────────────────────────────────────────────────────────────
@api_router.get("/video_feed/{camera_id}", summary="MJPEG video feed")
async def video_feed(camera_id: str, detect: str = "true", selected_worker: str = ""):
    detect_param = detect.lower() == "true"
    return StreamingResponse(
        get_video_stream_async(camera_id, detect_people=detect_param, selected_worker=selected_worker),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── AI Analytics Control ──────────────────────────────────────────────────────
class StartAnalyticsModel(BaseModel):
    modules: List[str]
    cameras: List[str]


@api_router.post("/api/ai_analytics/start", summary="Start AI analytics modules")
def start_ai_analytics(
    data: StartAnalyticsModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    cameras_str = [str(c) for c in data.cameras]
    with state.state_lock:
        active_cams = list(state.active_ai_modules.keys())

    for cam_id in active_cams:
        if cam_id not in cameras_str:
            state.clear_ai_module(cam_id)
            toggle_background_tracking(cam_id, False)
            state.add_real_log(cam_id, f"Cam {cam_id}", "SYSTEM", "INFO", "AI modules stopped.")

    for cam in cameras_str:
        state.set_ai_modules(cam, data.modules)
        mods_str = ", ".join(data.modules)
        toggle_background_tracking(cam, True)
        state.add_real_log(cam, f"Cam {cam}", "SYSTEM", "INFO", f"AI modules [{mods_str}] started.")

    return {"success": True}


class StopAnalyticsModel(BaseModel):
    cameras: List[str]


@api_router.post("/api/ai_analytics/stop", summary="Stop AI analytics modules")
def stop_ai_analytics(
    data: StopAnalyticsModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    for cam in data.cameras:
        cam_str = str(cam)
        state.clear_ai_module(cam_str)
        toggle_background_tracking(cam_str, False)
        state.add_real_log(cam_str, f"Cam {cam}", "SYSTEM", "INFO", "AI modules stopped.")
        with state.state_lock:
            if isinstance(state.shared_stats, dict) and "cameras" in state.shared_stats:
                for c in state.shared_stats["cameras"]:
                    if str(c.get("id")) == cam_str:
                        c["person_count"] = 0
                        c["tracked_positions"] = []
                state.shared_stats["person_count"] = sum(
                    c.get("person_count", 0) for c in state.shared_stats["cameras"]
                )

    from backend.ai.vlm_integration import clear_vlm_queue
    clear_vlm_queue()
    return {"success": True}


# ── Celery Task Endpoints ─────────────────────────────────────────────────────
class YoloInferenceModel(BaseModel):
    image_base64: str
    confidence: float = 0.5


@api_router.post("/api/infer/yolo", summary="Trigger async YOLO inference task")
def trigger_yolo(
    data: YoloInferenceModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    task = run_yolo_inference.delay(data.image_base64, data.confidence)
    return {"task_id": str(task.id), "status": "processing"}


class VlmPromptModel(BaseModel):
    image_base64: str
    prompt: str


@api_router.post("/api/infer/vlm", summary="Trigger async VLM prompt task")
def trigger_vlm(
    data: VlmPromptModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    task = run_vlm_prompt.delay(data.image_base64, data.prompt)
    return {"task_id": str(task.id), "status": "processing"}


@api_router.get("/api/result/{task_id}", summary="Poll async task result")
def get_task_result(task_id: str, current_user: dict = Depends(get_current_user)):
    task = AsyncResult(task_id)
    if task.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}
    elif task.state == "SUCCESS":
        return {"task_id": task_id, "status": "completed", "result": task.result}
    elif task.state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(task.info)}
    return {"task_id": task_id, "status": task.state}


# ── Alerts ────────────────────────────────────────────────────────────────────
@api_router.get("/api/alerts/unread", summary="Get unread alert count")
def get_unread_count(current_user: dict = Depends(get_current_user)):
    return {"count": state.get_unread_count()}


@api_router.delete("/api/alert_logs/{alert_id}", summary="Dismiss a single alert")
def dismiss_alert(
    alert_id: int,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    database.run_query("DELETE FROM alert_logs WHERE id = ?", (alert_id,))
    state._broadcast_alert({"type": "DISMISS", "id": alert_id})
    return {"success": True}


@api_router.post("/api/alert_logs/{alert_id}/verify", summary="Manually verify an alert")
def manually_verify_alert(
    alert_id: int,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    updated = database.update_alert_vlm(alert_id, "VERIFIED", f"Manually verified by {current_user['username']}.")
    if updated:
        updated["is_update"] = True
        state._broadcast_alert(updated)
    return {"success": True}


@api_router.get("/api/alerts/stream", summary="SSE stream for real-time alerts")
async def alert_stream(request: Request):
    async def event_generator():
        import queue
        import asyncio
        q = state.subscribe_alerts()
        last_heartbeat = time.time()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    alert = q.get_nowait()
                    yield f"data: {json.dumps(alert)}\n\n"
                except queue.Empty:
                    if time.time() - last_heartbeat > 30:
                        yield ": heartbeat\n\n"
                        last_heartbeat = time.time()
                    await asyncio.sleep(0.5)
                except Exception:
                    break
        finally:
            state.unsubscribe_alerts(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Logs Management ───────────────────────────────────────────────────────────
@api_router.get("/api/test_logs")
def get_test_logs(current_user: dict = Depends(get_current_user)):
    return database.get_recent_test_system_logs()


@api_router.post("/api/logs/clear")
def clear_logs(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_system_logs(is_test=False)
    return {"success": True}


@api_router.post("/api/test_logs/clear")
def clear_test_logs(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_system_logs(is_test=True)
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}


@api_router.get("/api/test_vlm_logs")
def get_test_vlm_logs(current_user: dict = Depends(get_current_user)):
    return database.get_recent_test_vlm_logs()


@api_router.post("/api/vlm_logs/clear")
def clear_vlm_logs(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_vlm_logs(is_test=False)
    return {"success": True}


@api_router.post("/api/test_vlm_logs/clear")
def clear_test_vlm_logs(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_vlm_logs(is_test=True)
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}


@api_router.post("/api/gate_events/clear")
def clear_gate_events(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_gate_events()
    return {"success": True}


@api_router.get("/api/test_alert_logs")
def get_test_alert_logs(current_user: dict = Depends(get_current_user)):
    return database.get_recent_test_alert_logs()


@api_router.post("/api/alert_logs/clear")
def clear_alert_logs(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_alert_logs(is_test=False)
    state.reset_unread_count()
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}


@api_router.post("/api/test_alert_logs/clear")
def clear_test_alert_logs(current_user: dict = Depends(require_role("admin", "safety_manager"))):
    database.clear_alert_logs(is_test=True)
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}


# ── Tracking & Gate Counting ──────────────────────────────────────────────────
@api_router.post("/api/map_tracking/{camera_id}/{status_str}")
def map_tracking_route(
    camera_id: str,
    status_str: str,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    is_active = status_str.lower() == "on"
    toggle_background_tracking(camera_id, is_active)
    if not is_active:
        with state.state_lock:
            if isinstance(state.shared_stats, dict) and "cameras" in state.shared_stats:
                for c in state.shared_stats["cameras"]:
                    if str(c.get("id")) == str(camera_id):
                        c["person_count"] = 0
                        c["tracked_positions"] = []
                state.shared_stats["person_count"] = sum(
                    c.get("person_count", 0) for c in state.shared_stats["cameras"]
                )
    return {"success": True, "camera_id": camera_id, "tracking": is_active}


@api_router.post("/api/gate_counting/{camera_id}/{status_str}")
def gate_counting_route(
    camera_id: str,
    status_str: str,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    is_active = status_str.lower() == "on"
    from backend.stream.streamer import toggle_gate_counting
    toggle_gate_counting(camera_id, is_active)
    return {"success": True, "camera_id": camera_id, "gate_counting": is_active}


class TrailDurationModel(BaseModel):
    duration: int


@api_router.get("/api/trail_settings")
def get_trail_settings(current_user: dict = Depends(get_current_user)):
    return {"duration": getattr(state, "trail_duration", 60)}


@api_router.post("/api/trail_settings")
def set_trail_settings(
    data: TrailDurationModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    state.trail_duration = data.duration
    return {"success": True, "duration": state.trail_duration}


class ClickModel(BaseModel):
    x: float
    y: float


@api_router.post("/api/click_video/{camera_id}")
def click_video_route(
    camera_id: str,
    data: ClickModel,
    current_user: dict = Depends(get_current_user),
):
    worker_id = process_video_click(camera_id, data.x, data.y)
    return {"success": True, "worker_id": worker_id}


# ── MediaMTX Auth Hook ────────────────────────────────────────────────────────
class MediaMtxAuthModel(BaseModel):
    ip: str
    user: str
    password: str
    path: str
    action: str


@api_router.post("/api/auth_stream", summary="MediaMTX stream auth hook")
def auth_stream_route(data: MediaMtxAuthModel):
    if data.action == "publish":
        return Response(status_code=200)

    if data.user == INTERNAL_YOLO_USER and data.password == INTERNAL_YOLO_SECRET:
        return Response(status_code=200)

    camera_id = data.path.split("_")[-1] if "stream_" in data.path else ""
    now = time.time()
    valid = False

    for tok, details in list(ACTIVE_TOKENS.items()):
        if details["expires_at"] < now:
            del ACTIVE_TOKENS[tok]
            continue
        if tok == data.password and str(details["camera_id"]) == str(camera_id):
            valid = True
            del ACTIVE_TOKENS[tok]
            break

    if valid:
        return Response(status_code=200)

    raise HTTPException(status_code=401, detail="Unauthorized stream token.")
# ── Phase 4: Webhooks ─────────────────────────────────────────────────────────
class WebhookModel(BaseModel):
    name: str
    endpoint_url: str
    secret: Optional[str] = None
    event_types: list = []

@api_router.post("/api/webhooks")
def create_webhook(data: WebhookModel, current_user: dict = Depends(require_role("admin"))):
    tenant_id = current_user.get("tenant_id", "default")
    events_json = json.dumps(data.event_types)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_query(
        "INSERT INTO webhooks (tenant_id, name, endpoint_url, secret, event_types, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (tenant_id, data.name, data.endpoint_url, data.secret, events_json, timestamp)
    )
    return {"success": True}

@api_router.get("/api/webhooks")
def get_webhooks(current_user: dict = Depends(require_role("admin"))):
    tenant_id = current_user.get("tenant_id", "default")
    webhooks = run_query("SELECT * FROM webhooks WHERE tenant_id = ?", (tenant_id,), fetch_mode="all")
    return webhooks

# ── Phase 4: API Keys ─────────────────────────────────────────────────────────
class ApiKeyModel(BaseModel):
    name: str

import hashlib
import secrets

@api_router.post("/api/keys")
def create_api_key(data: ApiKeyModel, current_user: dict = Depends(require_role("admin"))):
    tenant_id = current_user.get("tenant_id", "default")
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    run_query(
        "INSERT INTO api_keys (key_hash, name, tenant_id, created_at) VALUES (?, ?, ?, ?)",
        (key_hash, data.name, tenant_id, timestamp)
    )
    # Only return the raw key ONCE upon creation
    return {"success": True, "api_key": raw_key}

@api_router.get("/api/keys")
def get_api_keys(current_user: dict = Depends(require_role("admin"))):
    tenant_id = current_user.get("tenant_id", "default")
    keys = run_query("SELECT id, name, created_at, is_active FROM api_keys WHERE tenant_id = ?", (tenant_id,), fetch_mode="all")
    return keys

