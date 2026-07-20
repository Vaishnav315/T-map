"""
SentinelIQ AI Safety Platform — SaaS & Multi-Tenant API Routes
==========================================================
Provides:
  - Tenant CRUD (admin only)
  - User role management per tenant
  - Usage metrics per tenant
  - Plan/limits enforcement
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from backend.core import database
from backend.api.routes import get_current_user, require_role

saas_router = APIRouter(prefix="/api/saas", tags=["SaaS / Multi-Tenant"])


# ── Models ────────────────────────────────────────────────────────────────────
class CreateTenantModel(BaseModel):
    id: str          # Slug: "acme-corp"
    name: str        # Display name: "Acme Corporation"
    plan: str = "starter"
    max_cameras: int = 10

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        v = v.strip().lower()
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Tenant ID must be alphanumeric with hyphens only (e.g., 'acme-corp')")
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Tenant ID must be 3–50 characters.")
        return v

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        valid = {"starter", "professional", "enterprise"}
        if v not in valid:
            raise ValueError(f"Plan must be one of: {valid}")
        return v


class UpdateTenantModel(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    max_cameras: Optional[int] = None
    retention_days: Optional[int] = None
    is_active: Optional[bool] = None


class UpdateUserRoleModel(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = {"admin", "safety_manager", "viewer"}
        if v not in valid:
            raise ValueError(f"Role must be one of: {valid}")
        return v


# ── Tenant Endpoints ──────────────────────────────────────────────────────────
@saas_router.get("/tenants", summary="List all tenants (super admin only)")
def list_tenants(
    current_user: dict = Depends(require_role("admin")),
):
    """Returns all tenant organizations. Restricted to global admins."""
    tenants = database.list_tenants()
    return {"tenants": tenants, "count": len(tenants)}


@saas_router.post("/tenants", summary="Create a new tenant organization")
def create_tenant(
    data: CreateTenantModel,
    current_user: dict = Depends(require_role("admin")),
):
    success = database.create_tenant(
        tenant_id=data.id,
        name=data.name,
        plan=data.plan,
        max_cameras=data.max_cameras,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with ID '{data.id}' already exists.",
        )
    tenant = database.get_tenant(data.id)
    return {"message": "Tenant created successfully.", "tenant": tenant}


@saas_router.get("/tenants/{tenant_id}", summary="Get tenant details")
def get_tenant(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    # Users can only view their own tenant unless they are admin
    if current_user.get("role") != "admin" and current_user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    tenant = database.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    # Attach live usage metrics
    users = database.list_users_for_tenant(tenant_id)
    integrations = database.list_camera_integrations(tenant_id)
    total_cameras = sum(i.get("camera_count", 0) for i in integrations)

    return {
        **tenant,
        "usage": {
            "user_count": len(users),
            "camera_count": total_cameras,
            "integrations": len(integrations),
        },
    }


@saas_router.patch("/tenants/{tenant_id}", summary="Update tenant configuration")
def update_tenant(
    tenant_id: str,
    data: UpdateTenantModel,
    current_user: dict = Depends(require_role("admin")),
):
    tenant = database.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    database.update_tenant(tenant_id, **updates)
    return {"message": "Tenant updated.", "tenant": database.get_tenant(tenant_id)}


@saas_router.delete("/tenants/{tenant_id}", summary="Deactivate a tenant")
def deactivate_tenant(
    tenant_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    if tenant_id == "default":
        raise HTTPException(status_code=400, detail="Cannot deactivate the default tenant.")
    database.update_tenant(tenant_id, is_active=False)
    return {"message": f"Tenant '{tenant_id}' deactivated."}


# ── User Management Within Tenant ─────────────────────────────────────────────
@saas_router.get("/tenants/{tenant_id}/users", summary="List users in a tenant")
def list_tenant_users(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "safety_manager") and current_user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    users = database.list_users_for_tenant(tenant_id)
    return {"users": users, "count": len(users)}


@saas_router.patch("/tenants/{tenant_id}/users/{username}/role", summary="Update a user's role")
def update_user_role(
    tenant_id: str,
    username: str,
    data: UpdateUserRoleModel,
    current_user: dict = Depends(require_role("admin")),
):
    user = database.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="User does not belong to this tenant.")

    database.run_query(
        "UPDATE users SET role = ? WHERE username = ? AND tenant_id = ?",
        (data.role, username, tenant_id),
    )
    return {"message": f"Role for '{username}' updated to '{data.role}'."}


# ── My Tenant (self-service) ──────────────────────────────────────────────────
@saas_router.get("/my-tenant", summary="Get current user's tenant info")
def get_my_tenant(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "default")
    tenant = database.get_tenant(tenant_id)
    if not tenant:
        return {"id": "default", "name": "Default Organization", "plan": "enterprise"}

    users = database.list_users_for_tenant(tenant_id)
    integrations = database.list_camera_integrations(tenant_id)
    total_cameras = sum(i.get("camera_count", 0) for i in integrations)

    return {
        **tenant,
        "usage": {
            "user_count": len(users),
            "camera_count": total_cameras,
            "integrations": len(integrations),
        },
    }


# ── Plan Limits ───────────────────────────────────────────────────────────────
PLAN_LIMITS = {
    "starter":      {"max_cameras": 10,  "max_users": 3,  "retention_days": 7},
    "professional": {"max_cameras": 50,  "max_users": 10, "retention_days": 30},
    "enterprise":   {"max_cameras": 500, "max_users": 100, "retention_days": 365},
}


@saas_router.get("/plans", summary="Get available SaaS plan tiers")
def list_plans():
    return {
        "plans": [
            {
                "id": plan_id,
                "name": plan_id.capitalize(),
                **limits,
            }
            for plan_id, limits in PLAN_LIMITS.items()
        ]
    }
