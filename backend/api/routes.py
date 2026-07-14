import time
import os
import json
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Response, HTTPException, status, Depends
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from backend.core import state
from backend.core import database
from backend.core.config_loader import loader
from backend.stream.streamer import get_video_stream, get_video_stream_async, toggle_background_tracking, process_video_click
from backend.tasks import run_yolo_inference, run_vlm_prompt
from celery.result import AsyncResult

api_router = APIRouter()

EVIDENCE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "evidence"))
ACTIVE_TOKENS = {}
INTERNAL_YOLO_USER = "yolo_backend"
INTERNAL_YOLO_SECRET = "TaslSentinelYoloLocalSecret#"

# --- JWT Configuration ---
SECRET_KEY = "super_secret_production_key_change_me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
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

# --- Auth Endpoints ---
class SignupModel(BaseModel):
    username: str
    email: str
    password: str

@api_router.post("/api/signup")
def signup(user: SignupModel):
    success = database.create_user(user.username, user.email, user.password)
    if not success:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    return {"message": "User created successfully"}

@api_router.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = database.get_user(form_data.username)
    if not user or not database.verify_password(form_data.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@api_router.get("/api/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["username"], "email": current_user["email"]}

# --- Original Endpoints ---
@api_router.get("/api/stats")
def get_stats():
    with state.state_lock:
        stats = state.shared_stats.copy()
        stats['unread_alerts'] = state._unread_alert_count
        try:
            daily_counts = database.get_daily_gate_counts()
            stats['global_gate_in'] = daily_counts.get("IN", 0)
            stats['global_gate_out'] = daily_counts.get("OUT", 0)
        except Exception as e:
            print(f"[API] Error fetching daily counts: {e}")
        return stats

@api_router.get("/api/logs")
def get_logs():
    return database.get_recent_system_logs()

@api_router.get("/api/gate_events")
def get_gate_events():
    return database.get_recent_gate_events()

@api_router.get("/api/alert_logs")
def get_alert_logs():
    return database.get_recent_alert_logs()

@api_router.get("/api/vlm_logs")
def get_vlm_logs():
    return database.get_recent_vlm_logs()

@api_router.post("/api/alerts/mark_read")
def mark_alerts_read():
    state.reset_unread_count()
    return {"success": True}

@api_router.get("/evidence/{filename}")
def serve_evidence(filename: str):
    file_path = os.path.join(EVIDENCE_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Evidence not found")
    return FileResponse(file_path)

@api_router.get("/api/config/cameras")
def get_cameras_config():
    registry = loader.get_camera_registry()
    layouts = loader.get_map_layout()
    merged_cameras = []
    
    real_coords = {
        "28": [17.2439174, 78.5403015],
        "27": [17.2438281, 78.5407760],
        "33": [17.2439568, 78.5405590],
        "35": [17.2440603, 78.5414556],
        "3": [17.2444810, 78.5418086]
    }
    
    for cam_id, info in registry.items():
        layout = layouts.get(cam_id)
        px = layout.get("Percentage_X") if layout else None
        py = layout.get("Percentage_Y") if layout else None
        viewing_angle = layout.get("Viewing_Angle", 0) if layout else 0
            
        blueprint_coords = [round((py / 100.0) * 1290.0, 2), round((px / 100.0) * 2048.0, 2)] if px and py else None
        coords = real_coords.get(cam_id)
        
        # Do not fallback to a grid of fake GPS coordinates for geographic maps

        accessible = cam_id not in ["145", "102", "105"]
        status_msg = "ONLINE / ACCESSIBLE" if accessible else "OFFLINE/DENIED"
            
        merged_cameras.append({
            "id": cam_id,
            "name": info.get("Name", f"Cam {cam_id}"),
            "ip": info.get("IP", "127.0.0.1"),
            "brand": info.get("Brand", "Generic"),
            "area": info.get("Allocation", "Perimeter/Logistics"),
            "coords": coords,
            "blueprint_coords": blueprint_coords,
            "percentage_x": px,
            "percentage_y": py,
            "viewing_angle": viewing_angle,
            "accessible": accessible,
            "status": status_msg
        })
    return merged_cameras

@api_router.get("/api/stream_token/{camera_id}")
def get_stream_token(camera_id: str):
    token = secrets.token_hex(16)
    ACTIVE_TOKENS[token] = {
        "camera_id": camera_id,
        "expires_at": time.time() + 60.0
    }
    return {"success": True, "token": token, "path": f"live/stream_{camera_id}"}

@api_router.get("/video_feed/{camera_id}")
async def video_feed(camera_id: str, detect: str = 'true', selected_worker: str = ''):
    detect_param = detect.lower() == 'true'
    return StreamingResponse(
        get_video_stream_async(camera_id, detect_people=detect_param, selected_worker=selected_worker),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )

class StartAnalyticsModel(BaseModel):
    modules: List[str]
    cameras: List[str]

@api_router.post("/api/ai_analytics/start")
def start_ai_analytics(data: StartAnalyticsModel):
    modules = data.modules
    cameras_str = [str(c) for c in data.cameras]
    
    with state.state_lock:
        active_cams = list(state.active_ai_modules.keys())
        
    for cam_id in active_cams:
        if cam_id not in cameras_str:
            state.clear_ai_module(cam_id)
            toggle_background_tracking(cam_id, False)
            state.add_real_log(cam_id, f"Cam {cam_id}", "SYSTEM", "INFO", "AI modules stopped.")

    for cam in cameras_str:
        state.set_ai_modules(cam, modules)
        mods_str = ", ".join(modules)
        toggle_background_tracking(cam, True)
        state.add_real_log(cam, f"Cam {cam}", "SYSTEM", "INFO", f"AI modules [{mods_str}] started.")
    return {"success": True}

class StopAnalyticsModel(BaseModel):
    cameras: List[str]

@api_router.post("/api/ai_analytics/stop")
def stop_ai_analytics(data: StopAnalyticsModel):
    for cam in data.cameras:
        cam_str = str(cam)
        state.clear_ai_module(cam_str)
        toggle_background_tracking(cam_str, False)
        state.add_real_log(cam_str, f"Cam {cam}", "SYSTEM", "INFO", "AI modules stopped.")
        with state.state_lock:
            if isinstance(state.shared_stats, dict) and 'cameras' in state.shared_stats:
                for c in state.shared_stats['cameras']:
                    if str(c.get('id')) == cam_str:
                        c['person_count'] = 0
                        c['tracked_positions'] = []
                state.shared_stats['person_count'] = sum(
                    c.get('person_count', 0) for c in state.shared_stats['cameras'])
                
    from backend.ai.vlm_integration import clear_vlm_queue
    clear_vlm_queue()
    return {"success": True}

# --- Asynchronous Celery Tasks Endpoints ---
class YoloInferenceModel(BaseModel):
    image_base64: str
    confidence: float = 0.5

@api_router.post("/api/infer/yolo")
def trigger_yolo(data: YoloInferenceModel, current_user: dict = Depends(get_current_user)):
    task = run_yolo_inference.delay(data.image_base64, data.confidence)
    return {"task_id": str(task.id), "status": "processing"}

class VlmPromptModel(BaseModel):
    image_base64: str
    prompt: str

@api_router.post("/api/infer/vlm")
def trigger_vlm(data: VlmPromptModel, current_user: dict = Depends(get_current_user)):
    task = run_vlm_prompt.delay(data.image_base64, data.prompt)
    return {"task_id": str(task.id), "status": "processing"}

@api_router.get("/api/result/{task_id}")
def get_task_result(task_id: str, current_user: dict = Depends(get_current_user)):
    task = AsyncResult(task_id)
    if task.state == 'PENDING':
        return {"task_id": task_id, "status": "pending"}
    elif task.state == 'SUCCESS':
        return {"task_id": task_id, "status": "completed", "result": task.result}
    elif task.state == 'FAILURE':
        return {"task_id": task_id, "status": "failed", "error": str(task.info)}
    else:
        return {"task_id": task_id, "status": task.state}

# --- Missing Secondary Routes for Frontend ---

@api_router.get("/api/alerts/unread")
def get_unread_count():
    return {"count": state.get_unread_count()}

@api_router.delete("/api/alert_logs/{alert_id}")
def dismiss_alert(alert_id: int):
    """Dismiss (delete) a single alert by ID, broadcast removal to SSE clients."""
    database.run_query("DELETE FROM alert_logs WHERE id = ?", (alert_id,))
    state._broadcast_alert({"type": "DISMISS", "id": alert_id})
    return {"success": True}

@api_router.post("/api/alert_logs/{alert_id}/verify")
def manually_verify_alert(alert_id: int):
    """Manually mark an alert as VERIFIED with a manual note."""
    updated = database.update_alert_vlm(alert_id, "VERIFIED", "Manually verified by operator.")
    if updated:
        updated["is_update"] = True
        state._broadcast_alert(updated)
    return {"success": True}

@api_router.get("/api/alerts/stream")
async def alert_stream(request: Request):
    async def event_generator():
        q = state.subscribe_alerts()
        import queue
        import asyncio
        import time
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
                        yield f": heartbeat\n\n"
                        last_heartbeat = time.time()
                    await asyncio.sleep(0.5)
                except Exception:
                    break
        finally:
            state.unsubscribe_alerts(q)
            
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@api_router.get("/api/test_logs")
def get_test_logs():
    return database.get_recent_test_system_logs()

@api_router.post("/api/logs/clear")
def clear_logs():
    database.clear_system_logs(is_test=False)
    return {"success": True}

@api_router.post("/api/test_logs/clear")
def clear_test_logs():
    database.clear_system_logs(is_test=True)
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}

@api_router.get("/api/test_vlm_logs")
def get_test_vlm_logs():
    return database.get_recent_test_vlm_logs()

@api_router.post("/api/vlm_logs/clear")
def clear_vlm_logs():
    database.clear_vlm_logs(is_test=False)
    return {"success": True}

@api_router.post("/api/test_vlm_logs/clear")
def clear_test_vlm_logs():
    database.clear_vlm_logs(is_test=True)
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}

@api_router.post("/api/gate_events/clear")
def clear_gate_events():
    database.clear_gate_events()
    return {"success": True}

@api_router.get("/api/test_alert_logs")
def get_test_alert_logs():
    return database.get_recent_test_alert_logs()

@api_router.post("/api/alert_logs/clear")
def clear_alert_logs():
    database.clear_alert_logs(is_test=False)
    state.reset_unread_count()
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}

@api_router.post("/api/test_alert_logs/clear")
def clear_test_alert_logs():
    database.clear_alert_logs(is_test=True)
    state._broadcast_alert({"type": "CLEAR_ALL"})
    return {"success": True}

@api_router.post("/api/map_tracking/{camera_id}/{status}")
def map_tracking_route(camera_id: str, status: str):
    is_active = (status.lower() == 'on')
    toggle_background_tracking(camera_id, is_active)
    
    if not is_active:
        with state.state_lock:
            if isinstance(state.shared_stats, dict) and 'cameras' in state.shared_stats:
                for c in state.shared_stats['cameras']:
                    if str(c.get('id')) == str(camera_id):
                        c['person_count'] = 0
                        c['tracked_positions'] = []
                state.shared_stats['person_count'] = sum(
                    c.get('person_count', 0) for c in state.shared_stats['cameras'])
    return {"success": True, "camera_id": camera_id, "tracking": is_active}

@api_router.post("/api/gate_counting/{camera_id}/{status}")
def gate_counting_route(camera_id: str, status: str):
    is_active = (status.lower() == 'on')
    from backend.stream.streamer import toggle_gate_counting
    toggle_gate_counting(camera_id, is_active)
    return {"success": True, "camera_id": camera_id, "gate_counting": is_active}

class TrailDurationModel(BaseModel):
    duration: int

@api_router.get("/api/trail_settings")
def get_trail_settings():
    return {"duration": getattr(state, 'trail_duration', 60)}

@api_router.post("/api/trail_settings")
def set_trail_settings(data: TrailDurationModel):
    state.trail_duration = data.duration
    return {"success": True, "duration": state.trail_duration}

class ClickModel(BaseModel):
    x: float
    y: float

@api_router.post("/api/click_video/{camera_id}")
def click_video_route(camera_id: str, data: ClickModel):
    worker_id = process_video_click(camera_id, data.x, data.y)
    return {"success": True, "worker_id": worker_id}

class MediaMtxAuthModel(BaseModel):
    ip: str
    user: str
    password: str
    path: str
    action: str

@api_router.post("/api/auth_stream")
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
    else:
        print(f"[SECURITY AUTH FAILED] IP: {data.ip}, Path: {data.path}, Token: {data.password}")
        raise HTTPException(status_code=401, detail="Unauthorized stream token")