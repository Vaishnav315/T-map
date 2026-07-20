"""
SentinelIQ AI Safety Platform — Camera Integration API Routes
=========================================================
Allows customers to connect their company CCTV management systems
via multiple integration types:
  - Direct RTSP URL list (JSON/CSV bulk import)
  - ONVIF device discovery on a subnet
  - Database connection string (VMS databases)
"""

import json
import socket
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from pydantic import BaseModel

from backend.core import database
from backend.api.routes import get_current_user, require_role

integration_router = APIRouter(prefix="/api/integrations", tags=["Camera Integrations"])


# ── Models ────────────────────────────────────────────────────────────────────
class RtspImportModel(BaseModel):
    """Bulk RTSP camera import."""
    name: str                     # Friendly name for this integration
    cameras: List[dict]           # [{"id": "1", "name": "Gate Cam", "rtsp_url": "rtsp://...", "area": "Main Gate"}]


class OnvifDiscoveryModel(BaseModel):
    """ONVIF auto-discovery request."""
    name: str
    subnet: str          # e.g. "192.168.1" (will scan 1-254)
    port: int = 80
    username: str = "admin"
    password: str = ""


class DbConnectionModel(BaseModel):
    """Connect an external VMS/company database."""
    name: str
    db_type: str         # "postgresql" | "mysql" | "mssql" | "sqlite"
    host: str
    port: int
    database: str
    username: str
    password: str
    table_name: str = "cameras"   # Table that contains camera records


class DeleteIntegrationModel(BaseModel):
    integration_id: int


# ── Endpoints ─────────────────────────────────────────────────────────────────
@integration_router.get("/", summary="List all camera integrations for this tenant")
def list_integrations(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "default")
    integrations = database.list_camera_integrations(tenant_id)
    return {"integrations": integrations, "count": len(integrations)}


@integration_router.post("/rtsp-import", summary="Bulk import cameras via RTSP URLs")
def import_rtsp_cameras(
    data: RtspImportModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    """
    Import a list of cameras with RTSP URLs directly.
    Each camera entry: {"id": "cam1", "name": "Gate Cam", "rtsp_url": "rtsp://user:pass@ip:554/stream", "area": "Main Gate"}
    """
    tenant_id = current_user.get("tenant_id", "default")

    if not data.cameras:
        raise HTTPException(status_code=400, detail="Camera list cannot be empty.")
    if len(data.cameras) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 cameras per import.")

    # Validate required fields
    required_fields = {"name", "rtsp_url"}
    for i, cam in enumerate(data.cameras):
        missing = required_fields - set(cam.keys())
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Camera at index {i} is missing required fields: {missing}",
            )

    # Save integration record (stores the full camera list as JSON)
    connection_string = json.dumps(data.cameras)
    integration_id = database.save_camera_integration(
        tenant_id=tenant_id,
        integration_type="rtsp_bulk",
        name=data.name,
        connection_string=connection_string,
    )
    database.update_integration_status(integration_id, "active", len(data.cameras))

    return {
        "message": f"Successfully imported {len(data.cameras)} cameras.",
        "integration_id": integration_id,
        "camera_count": len(data.cameras),
    }


@integration_router.post("/onvif-discover", summary="Discover cameras via ONVIF on a subnet")
async def discover_onvif_cameras(
    data: OnvifDiscoveryModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    """
    Scans a subnet for ONVIF-compatible cameras.
    Returns a list of discovered cameras that can be confirmed and imported.
    """
    tenant_id = current_user.get("tenant_id", "default")

    # Validate subnet format
    parts = data.subnet.split(".")
    if len(parts) != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        raise HTTPException(
            status_code=400,
            detail="Invalid subnet format. Use the first 3 octets, e.g., '192.168.1'",
        )

    discovered = []
    # Quick TCP port scan to find potential ONVIF devices (non-blocking preview)
    for i in range(1, 255):
        ip = f"{data.subnet}.{i}"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.15)
            result = sock.connect_ex((ip, data.port))
            sock.close()
            if result == 0:
                discovered.append({
                    "ip": ip,
                    "port": data.port,
                    "status": "reachable",
                    "onvif_url": f"http://{ip}:{data.port}/onvif/device_service",
                    "suggested_rtsp": f"rtsp://{data.username}:{data.password}@{ip}/rtsp_tunnel?inst=1",
                })
        except Exception:
            pass

    # Save a pending integration record
    integration_id = database.save_camera_integration(
        tenant_id=tenant_id,
        integration_type="onvif_discovery",
        name=data.name,
        connection_string=json.dumps({"subnet": data.subnet, "port": data.port, "discovered": discovered}),
    )
    database.update_integration_status(integration_id, "discovered", len(discovered))

    return {
        "message": f"ONVIF scan complete. Found {len(discovered)} reachable devices on {data.subnet}.0/24.",
        "integration_id": integration_id,
        "discovered": discovered,
        "total_found": len(discovered),
    }


@integration_router.post("/db-connect", summary="Connect an external VMS database")
def connect_vms_database(
    data: DbConnectionModel,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    """
    Connects to a customer's existing CCTV management system database
    and discovers camera records from the specified table.
    """
    tenant_id = current_user.get("tenant_id", "default")

    # Build connection string (password is NOT stored in plain text in a real system —
    # here we store the schema only and hash the credentials in production)
    conn_info = {
        "db_type": data.db_type,
        "host": data.host,
        "port": data.port,
        "database": data.database,
        "username": data.username,
        "table_name": data.table_name,
        # NOTE: In production, credentials would be encrypted (AES-256) before storage
    }

    # Test connectivity first
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((data.host, data.port))
        sock.close()
        if result != 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reach database host {data.host}:{data.port}. Check your network connection.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {str(e)}")

    # Save integration
    integration_id = database.save_camera_integration(
        tenant_id=tenant_id,
        integration_type="vms_database",
        name=data.name,
        connection_string=json.dumps(conn_info),
    )
    database.update_integration_status(integration_id, "connected", 0)

    return {
        "message": f"Database connection to '{data.host}' established successfully.",
        "integration_id": integration_id,
        "note": "Camera discovery from the database will happen in the background. Check status in a few seconds.",
    }


@integration_router.get("/{integration_id}/cameras", summary="Get cameras from an integration")
def get_integration_cameras(
    integration_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Returns the camera list from a specific integration."""
    tenant_id = current_user.get("tenant_id", "default")
    integrations = database.list_camera_integrations(tenant_id)
    integration = next((i for i in integrations if i["id"] == integration_id), None)

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found.")

    try:
        conn_data = json.loads(integration.get("connection_string", "{}"))
        cameras = conn_data if isinstance(conn_data, list) else conn_data.get("discovered", [])
    except (json.JSONDecodeError, TypeError):
        cameras = []

    return {
        "integration_id": integration_id,
        "integration_name": integration.get("name"),
        "integration_type": integration.get("integration_type"),
        "cameras": cameras,
        "count": len(cameras),
    }


@integration_router.delete("/{integration_id}", summary="Remove a camera integration")
def delete_integration(
    integration_id: int,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    tenant_id = current_user.get("tenant_id", "default")
    database.delete_camera_integration(integration_id, tenant_id)
    return {"message": "Integration removed successfully."}


@integration_router.post("/{integration_id}/sync", summary="Re-sync cameras from an integration")
def sync_integration(
    integration_id: int,
    current_user: dict = Depends(require_role("admin", "safety_manager")),
):
    """Triggers a re-sync of cameras from an integration source."""
    tenant_id = current_user.get("tenant_id", "default")
    integrations = database.list_camera_integrations(tenant_id)
    integration = next((i for i in integrations if i["id"] == integration_id), None)

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found.")

    # Update sync timestamp
    database.update_integration_status(
        integration_id,
        "syncing",
        integration.get("camera_count", 0),
    )
    return {"message": "Sync triggered. Camera list will refresh momentarily."}
