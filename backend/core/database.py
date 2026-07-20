"""
SentinelIQ AI Safety Platform — Database Layer
==========================================
Dual-mode: SQLite WAL (development/edge) or PostgreSQL (production SaaS).
Includes:
  - Multi-tenant schema (tenant_id on all tables)
  - Role-based user accounts (admin / safety_manager / viewer)
  - Non-destructive ensure_schema() migration
  - Thread-safe connection pooling
"""

import sqlite3
import os
import threading
from datetime import datetime, timedelta

DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "sentineliq_history.db")
)
DATABASE_URL = os.getenv("DATABASE_URL", "")
_db_lock = threading.Lock()

IS_POSTGRES = False
if DATABASE_URL:
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        conn.close()
        IS_POSTGRES = True
        print(f"[DATABASE] Connected to PostgreSQL: {DATABASE_URL.split('@')[-1]}")
    except Exception as e:
        print(f"[DATABASE WARNING] Postgres connection failed ({e}). Falling back to SQLite.")


# ── Connection Factory ────────────────────────────────────────────────────────
def get_connection():
    if IS_POSTGRES:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        return conn


# ── Unified Query Executor ────────────────────────────────────────────────────
def run_query(query, params=None, fetch_mode=None, returning_id_field=None):
    """
    Thread-safe unified query executor.
    fetch_mode: 'one' | 'all' | None
    """
    if params is None:
        params = ()

    with _db_lock:
        conn = get_connection()
        if IS_POSTGRES:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            query = query.replace("?", "%s")
            if returning_id_field and "INSERT INTO" in query:
                query += f" RETURNING {returning_id_field}"
        else:
            cur = conn.cursor()

        try:
            cur.execute(query, params)
            result = None
            if returning_id_field and IS_POSTGRES and "INSERT INTO" in query:
                result = cur.fetchone()[0]
            elif fetch_mode == "one":
                row = cur.fetchone()
                result = dict(row) if row else None
            elif fetch_mode == "all":
                rows = cur.fetchall()
                result = [dict(row) for row in rows]
            else:
                if returning_id_field and not IS_POSTGRES and "INSERT INTO" in query:
                    cur.execute("SELECT last_insert_rowid()")
                    result = cur.fetchone()[0]
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()


# ── Schema Migration (non-destructive) ───────────────────────────────────────
def ensure_schema():
    """
    Creates or migrates all tables. Safe to run on every startup.
    Adds missing columns to existing tables without data loss.
    """
    _create_tables()
    _migrate_existing_tables()


def _create_tables():
    """Create all tables if they don't exist yet."""
    conn = get_connection()
    cur = conn.cursor()

    if IS_POSTGRES:
        stmts = [
            # ── SaaS: Tenants ──────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                plan VARCHAR(50) DEFAULT 'starter',
                max_cameras INTEGER DEFAULT 10,
                retention_days INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT TRUE,
                created_at VARCHAR(50),
                settings JSONB DEFAULT '{}'
            )
            """,
            # ── Users ─────────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'viewer',
                tenant_id VARCHAR(50) DEFAULT 'default',
                created_at VARCHAR(50),
                last_login VARCHAR(50)
            )
            """,
            # ── System Logs ───────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                camera_id VARCHAR(50),
                camera_name VARCHAR(100),
                type VARCHAR(50),
                severity VARCHAR(50),
                details TEXT,
                tenant_id VARCHAR(50) DEFAULT 'default'
            )
            """,
            # ── VLM Logs ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS vlm_logs (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                camera_id VARCHAR(50),
                camera_name VARCHAR(100),
                severity VARCHAR(50),
                details TEXT,
                tenant_id VARCHAR(50) DEFAULT 'default'
            )
            """,
            # ── Alert Logs ────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS alert_logs (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                camera_id VARCHAR(50),
                camera_name VARCHAR(100),
                type VARCHAR(50),
                severity VARCHAR(50),
                details TEXT,
                evidence TEXT,
                vlm_status VARCHAR(50) DEFAULT 'PENDING',
                vlm_description TEXT DEFAULT NULL,
                tenant_id VARCHAR(50) DEFAULT 'default'
            )
            """,
            # ── Gate Events ───────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS gate_events (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                event_type VARCHAR(50),
                leaflet_y REAL,
                leaflet_x REAL,
                tenant_id VARCHAR(50) DEFAULT 'default'
            )
            """,
            # ── Camera Integrations ───────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS camera_integrations (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(50) DEFAULT 'default',
                integration_type VARCHAR(50),
                name VARCHAR(200),
                connection_string TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                last_synced VARCHAR(50),
                camera_count INTEGER DEFAULT 0,
                created_at VARCHAR(50)
            )
            """,
            # ── Position Telemetry ────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS position_telemetry (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                camera_id VARCHAR(50),
                track_id INTEGER,
                x_pos REAL,
                y_pos REAL,
                tenant_id VARCHAR(50) DEFAULT 'default'
            )
            """,
            # ── API Keys ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                key_hash VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                tenant_id VARCHAR(50) DEFAULT 'default',
                created_at VARCHAR(50),
                expires_at VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                scopes JSONB DEFAULT '[]'
            )
            """,
            # ── Webhooks ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(50) DEFAULT 'default',
                name VARCHAR(100),
                endpoint_url TEXT NOT NULL,
                secret VARCHAR(255),
                event_types JSONB DEFAULT '[]',
                is_active BOOLEAN DEFAULT TRUE,
                created_at VARCHAR(50),
                last_triggered VARCHAR(50),
                failure_count INTEGER DEFAULT 0
            )
            """,
        ]
    else:
        stmts = [
            # ── SaaS: Tenants ──────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan TEXT DEFAULT 'starter',
                max_cameras INTEGER DEFAULT 10,
                retention_days INTEGER DEFAULT 30,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                settings TEXT DEFAULT '{}'
            )
            """,
            # ── Users ─────────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'viewer',
                tenant_id TEXT DEFAULT 'default',
                created_at TEXT,
                last_login TEXT
            )
            """,
            # ── System Logs ───────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                camera_id TEXT,
                camera_name TEXT,
                type TEXT,
                severity TEXT,
                details TEXT,
                tenant_id TEXT DEFAULT 'default'
            )
            """,
            # ── VLM Logs ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS vlm_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                camera_id TEXT,
                camera_name TEXT,
                severity TEXT,
                details TEXT,
                tenant_id TEXT DEFAULT 'default'
            )
            """,
            # ── Alert Logs ────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                camera_id TEXT,
                camera_name TEXT,
                type TEXT,
                severity TEXT,
                details TEXT,
                evidence TEXT,
                vlm_status TEXT DEFAULT 'PENDING',
                vlm_description TEXT DEFAULT NULL,
                tenant_id TEXT DEFAULT 'default'
            )
            """,
            # ── Gate Events ───────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS gate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event_type TEXT,
                leaflet_y REAL,
                leaflet_x REAL,
                tenant_id TEXT DEFAULT 'default'
            )
            """,
            # ── Camera Integrations ───────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS camera_integrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT DEFAULT 'default',
                integration_type TEXT,
                name TEXT,
                connection_string TEXT,
                status TEXT DEFAULT 'pending',
                last_synced TEXT,
                camera_count INTEGER DEFAULT 0,
                created_at TEXT
            )
            """,
            # ── Position Telemetry ────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS position_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                camera_id TEXT,
                track_id INTEGER,
                x_pos REAL,
                y_pos REAL,
                tenant_id TEXT DEFAULT 'default'
            )
            """,
            # ── API Keys ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                tenant_id TEXT DEFAULT 'default',
                created_at TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1,
                scopes TEXT DEFAULT '[]'
            )
            """,
            # ── Webhooks ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT DEFAULT 'default',
                name TEXT,
                endpoint_url TEXT NOT NULL,
                secret TEXT,
                event_types TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                last_triggered TEXT,
                failure_count INTEGER DEFAULT 0
            )
            """,
        ]

    try:
        for stmt in stmts:
            cur.execute(stmt)

        # Ensure default tenant exists
        if IS_POSTGRES:
            cur.execute("""
                INSERT INTO tenants (id, name, plan, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, ("default", "Default Organization", "enterprise", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        else:
            cur.execute("""
                INSERT OR IGNORE INTO tenants (id, name, plan, created_at)
                VALUES (?, ?, ?, ?)
            """, ("default", "Default Organization", "enterprise", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        print("[DATABASE] Schema verified / created.")
    except Exception as e:
        conn.rollback()
        print(f"[DATABASE ERROR] Schema creation failed: {e}")
        raise
    finally:
        conn.close()


def _migrate_existing_tables():
    """
    Non-destructive migration: adds columns to existing tables if missing.
    Safe to run repeatedly — uses IF NOT EXISTS / exception-catching.
    """
    migrations = [
        # Add role column to users if missing
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'viewer'",
        "ALTER TABLE users ADD COLUMN tenant_id TEXT DEFAULT 'default'",
        "ALTER TABLE users ADD COLUMN last_login TEXT",
        # Add tenant_id to log tables if missing
        "ALTER TABLE system_logs ADD COLUMN tenant_id TEXT DEFAULT 'default'",
        "ALTER TABLE vlm_logs ADD COLUMN tenant_id TEXT DEFAULT 'default'",
        "ALTER TABLE alert_logs ADD COLUMN tenant_id TEXT DEFAULT 'default'",
        "ALTER TABLE gate_events ADD COLUMN tenant_id TEXT DEFAULT 'default'",
    ]

    conn = get_connection()
    cur = conn.cursor()
    for migration in migrations:
        try:
            if IS_POSTGRES:
                cur.execute(migration.replace("?", "%s"))
            else:
                cur.execute(migration)
            conn.commit()
        except Exception:
            # Column already exists — this is expected and safe
            conn.rollback()
    conn.close()


# ── Password Utilities ────────────────────────────────────────────────────────
try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    import hashlib, secrets as _sec
    _BCRYPT_AVAILABLE = False
    print("[DATABASE WARNING] bcrypt not found. Using SHA256 fallback (install bcrypt for production).")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if _BCRYPT_AVAILABLE:
            return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        else:
            salt, stored = hashed_password.split("$", 1)
            return hashlib.sha256((salt + plain_password).encode()).hexdigest() == stored
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    if _BCRYPT_AVAILABLE:
        salt = _bcrypt.gensalt()
        return _bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    else:
        salt = _sec.token_hex(16)
        hashed = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}${hashed}"


# ── User Management ───────────────────────────────────────────────────────────
def create_user(username: str, email: str, password: str, role: str = "viewer", tenant_id: str = "default") -> bool:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed = get_password_hash(password)
    try:
        run_query(
            "INSERT INTO users (username, email, password_hash, role, tenant_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, hashed, role, tenant_id, timestamp),
            returning_id_field="id",
        )
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "integrity" in err_str or "duplicate" in err_str:
            return False
        raise


def get_user(username: str) -> dict | None:
    return run_query(
        "SELECT * FROM users WHERE username = ?",
        (username,),
        fetch_mode="one",
    )


def update_last_login(username: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_query("UPDATE users SET last_login = ? WHERE username = ?", (timestamp, username))


# ── Tenant Management ─────────────────────────────────────────────────────────
def get_tenant(tenant_id: str) -> dict | None:
    return run_query("SELECT * FROM tenants WHERE id = ?", (tenant_id,), fetch_mode="one")


def list_tenants() -> list:
    return run_query("SELECT * FROM tenants ORDER BY created_at DESC", fetch_mode="all") or []


def create_tenant(tenant_id: str, name: str, plan: str = "starter", max_cameras: int = 10) -> bool:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        run_query(
            "INSERT INTO tenants (id, name, plan, max_cameras, created_at) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, name, plan, max_cameras, timestamp),
            returning_id_field="id",
        )
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "integrity" in err_str or "duplicate" in err_str:
            return False
        raise


def update_tenant(tenant_id: str, **kwargs) -> bool:
    allowed = {"name", "plan", "max_cameras", "retention_days", "is_active", "settings"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    run_query(
        f"UPDATE tenants SET {set_clause} WHERE id = ?",
        (*fields.values(), tenant_id),
    )
    return True


def list_users_for_tenant(tenant_id: str) -> list:
    return run_query(
        "SELECT id, username, email, role, tenant_id, created_at, last_login FROM users WHERE tenant_id = ? ORDER BY created_at DESC",
        (tenant_id,),
        fetch_mode="all",
    ) or []


# ── Logging Functions ─────────────────────────────────────────────────────────
def insert_system_log(camera_id, camera_name, event_type, severity, details, tenant_id="default"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_id = run_query(
        "INSERT INTO system_logs (timestamp, camera_id, camera_name, type, severity, details, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), camera_name, event_type, severity, details, tenant_id),
        returning_id_field="id",
    )
    return {"id": last_id, "timestamp": timestamp, "camera_id": camera_id,
            "camera_name": camera_name, "type": event_type, "severity": severity, "details": details}


def insert_vlm_log(camera_id, camera_name, severity, details, tenant_id="default"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_id = run_query(
        "INSERT INTO vlm_logs (timestamp, camera_id, camera_name, severity, details, tenant_id) VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), camera_name, severity, details, tenant_id),
        returning_id_field="id",
    )
    return {"id": last_id, "timestamp": timestamp, "camera_id": camera_id,
            "camera_name": camera_name, "severity": severity, "details": details}


def insert_alert_log(camera_id, camera_name, event_type, severity, details, evidence, vlm_status="PENDING", vlm_description=None, tenant_id="default"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_id = run_query(
        "INSERT INTO alert_logs (timestamp, camera_id, camera_name, type, severity, details, evidence, vlm_status, vlm_description, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), camera_name, event_type, severity, details, evidence, vlm_status, vlm_description, tenant_id),
        returning_id_field="id",
    )
    
    alert_data = {"id": last_id, "timestamp": timestamp, "camera_id": camera_id,
            "camera_name": camera_name, "type": event_type, "severity": severity,
            "details": details, "evidence": evidence, "vlm_status": vlm_status, "vlm_description": vlm_description}
            
    try:
        from backend.core.webhooks import dispatch_event
        dispatch_event("alert.created", alert_data, tenant_id)
    except Exception as e:
        print(f"[Webhook] Failed to import/dispatch: {e}")
        
    return alert_data


def update_alert_vlm(alert_id, vlm_status, vlm_description):
    run_query(
        "UPDATE alert_logs SET vlm_status = ?, vlm_description = ? WHERE id = ?",
        (vlm_status, vlm_description, alert_id),
    )
    alert = run_query("SELECT * FROM alert_logs WHERE id = ?", (alert_id,), fetch_mode="one")
    
    try:
        from backend.core.webhooks import dispatch_event
        dispatch_event("alert.vlm_updated", alert, alert.get("tenant_id", "default"))
    except Exception as e:
        print(f"[Webhook] Failed to import/dispatch: {e}")
        
    return alert

# ── Telemetry Logging ────────────────────────────────────────────────────────
def insert_position_telemetry(camera_id, track_id, x_pos, y_pos, tenant_id="default"):
    timestamp = datetime.now(timezone.utc).isoformat()
    return run_query(
        "INSERT INTO position_telemetry (timestamp, camera_id, track_id, x_pos, y_pos, tenant_id) VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), int(track_id), float(x_pos), float(y_pos), tenant_id),
        returning_id_field="id"
    )

def get_position_telemetry(hours=24, tenant_id=None):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    if tenant_id:
        return run_query(
            "SELECT * FROM position_telemetry WHERE tenant_id = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 50000",
            (tenant_id, since), fetch_mode="all"
        ) or []
    return run_query(
        "SELECT * FROM position_telemetry WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 50000",
        (since,), fetch_mode="all"
    ) or []


# ── Log Retrieval ─────────────────────────────────────────────────────────────
def get_recent_system_logs(limit=200, tenant_id=None):
    if tenant_id:
        return run_query(
            "SELECT * FROM system_logs WHERE camera_id NOT LIKE 'test_%' AND tenant_id = ? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit), fetch_mode="all",
        ) or []
    return run_query(
        "SELECT * FROM system_logs WHERE camera_id NOT LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,), fetch_mode="all",
    ) or []


def get_recent_test_system_logs(limit=200):
    return run_query(
        "SELECT * FROM system_logs WHERE camera_id LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,), fetch_mode="all",
    ) or []


def get_recent_vlm_logs(limit=200, tenant_id=None):
    if tenant_id:
        return run_query(
            "SELECT * FROM vlm_logs WHERE camera_id NOT LIKE 'test_%' AND tenant_id = ? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit), fetch_mode="all",
        ) or []
    return run_query(
        "SELECT * FROM vlm_logs WHERE camera_id NOT LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,), fetch_mode="all",
    ) or []


def get_recent_test_vlm_logs(limit=200):
    return run_query(
        "SELECT * FROM vlm_logs WHERE camera_id LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,), fetch_mode="all",
    ) or []


def get_recent_alert_logs(limit=200, tenant_id=None):
    if tenant_id:
        return run_query(
            "SELECT * FROM alert_logs WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit), fetch_mode="all",
        ) or []
    return run_query(
        "SELECT * FROM alert_logs ORDER BY id DESC LIMIT ?",
        (limit,), fetch_mode="all",
    ) or []


def get_recent_test_alert_logs(limit=200):
    return run_query(
        "SELECT * FROM alert_logs WHERE camera_id LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,), fetch_mode="all",
    ) or []


def get_recent_gate_events(limit=200, tenant_id=None):
    query = "SELECT * FROM gate_events ORDER BY id DESC LIMIT 5000"
    params = ()
    if tenant_id:
        query = "SELECT * FROM gate_events WHERE tenant_id = ? ORDER BY id DESC LIMIT 5000"
        params = (tenant_id,)

    raw_events = run_query(query, params, fetch_mode="all")
    if not raw_events:
        return []

    hourly_groups: dict = {}
    for ev in raw_events:
        ts = ev.get("timestamp")
        if not ts:
            continue
        hour_str = ts[:13] + ":00:00"
        if hour_str not in hourly_groups:
            hourly_groups[hour_str] = {"IN": 0, "OUT": 0, "timestamp": hour_str}
        etype = ev.get("event_type", "IN")
        if etype in hourly_groups[hour_str]:
            hourly_groups[hour_str][etype] += 1

    aggregated = []
    for i, hour in enumerate(sorted(hourly_groups.keys(), reverse=True)):
        if i >= limit:
            break
        counts = hourly_groups[hour]
        aggregated.append({
            "id": i + 1,
            "timestamp": counts["timestamp"],
            "camera_name": "GATE CAM 3",
            "camera_id": "3",
            "event_type": "HOURLY",
            "severity": "INFO",
            "details": f"Hourly traffic summary: {counts['IN']} IN, {counts['OUT']} OUT.",
        })
    return aggregated


def insert_gate_event(event_type, leaflet_y, leaflet_x, tenant_id="default"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_query(
        "INSERT INTO gate_events (timestamp, event_type, leaflet_y, leaflet_x, tenant_id) VALUES (?, ?, ?, ?, ?)",
        (timestamp, event_type, leaflet_y, leaflet_x, tenant_id),
    )


def delete_last_gate_event(event_type):
    run_query(
        "DELETE FROM gate_events WHERE id = (SELECT id FROM gate_events WHERE event_type = ? ORDER BY id DESC LIMIT 1)",
        (event_type,),
    )


def get_daily_gate_counts(tenant_id=None):
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    if tenant_id:
        rows = run_query(
            "SELECT event_type, COUNT(*) as count FROM gate_events WHERE timestamp >= ? AND tenant_id = ? GROUP BY event_type",
            (cutoff, tenant_id), fetch_mode="all",
        )
    else:
        rows = run_query(
            "SELECT event_type, COUNT(*) as count FROM gate_events WHERE timestamp >= ? GROUP BY event_type",
            (cutoff,), fetch_mode="all",
        )
    counts = {"IN": 0, "OUT": 0}
    if rows:
        for row in rows:
            if row["event_type"] in counts:
                counts[row["event_type"]] = row["count"]
    return counts


# ── Bulk Clear ────────────────────────────────────────────────────────────────
def clear_system_logs(is_test=False):
    run_query("DELETE FROM system_logs")


def clear_vlm_logs(is_test=False):
    run_query("DELETE FROM vlm_logs")


def clear_alert_logs(is_test=False):
    run_query("DELETE FROM alert_logs")


def clear_gate_events():
    run_query("DELETE FROM gate_events")


# ── Camera Integration Records ────────────────────────────────────────────────
def save_camera_integration(tenant_id: str, integration_type: str, name: str, connection_string: str) -> int:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return run_query(
        "INSERT INTO camera_integrations (tenant_id, integration_type, name, connection_string, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (tenant_id, integration_type, name, connection_string, timestamp),
        returning_id_field="id",
    )


def list_camera_integrations(tenant_id: str) -> list:
    return run_query(
        "SELECT * FROM camera_integrations WHERE tenant_id = ? ORDER BY created_at DESC",
        (tenant_id,), fetch_mode="all",
    ) or []


def update_integration_status(integration_id: int, status: str, camera_count: int = 0):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_query(
        "UPDATE camera_integrations SET status = ?, camera_count = ?, last_synced = ? WHERE id = ?",
        (status, camera_count, timestamp, integration_id),
    )


def delete_camera_integration(integration_id: int, tenant_id: str):
    run_query(
        "DELETE FROM camera_integrations WHERE id = ? AND tenant_id = ?",
        (integration_id, tenant_id),
    )
