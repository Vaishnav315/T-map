import sqlite3
import os
import threading
from datetime import datetime, timedelta

DB_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "tasl_history.db"))
DATABASE_URL = os.getenv("DATABASE_URL")
_db_lock = threading.Lock()

IS_POSTGRES = False
if DATABASE_URL:
    try:
        import psycopg2
        # Verify connection works, if it fails, fallback to SQLite
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        conn.close()
        IS_POSTGRES = True
        print(f"[DATABASE] Connected to central PostgreSQL database: {DATABASE_URL}")
    except Exception as e:
        print(f"[DATABASE WARNING] Failed to connect to Postgres ({e}). Falling back to SQLite.")

def get_connection():
    if IS_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

def run_query(query, params=None, fetch_mode=None, returning_id_field=None):
    """
    Unified query executor handling parameters, placeholders, locks, and fetch modes.
    fetch_mode: 'one', 'all', or None
    """
    if params is None:
        params = ()
    
    with _db_lock:
        conn = get_connection()
        
        if IS_POSTGRES:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Translate placeholder ? -> %s for Postgres
            query = query.replace("?", "%s")
            # If we need to return last inserted ID in postgres, append RETURNING ID
            if returning_id_field and "INSERT INTO" in query:
                query += f" RETURNING {returning_id_field}"
        else:
            cur = conn.cursor()
            
        try:
            cur.execute(query, params)
            
            result = None
            if returning_id_field and IS_POSTGRES and "INSERT INTO" in query:
                result = cur.fetchone()[0]
            elif fetch_mode == 'one':
                row = cur.fetchone()
                if row:
                    result = dict(row)
            elif fetch_mode == 'all':
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

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    if IS_POSTGRES:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                camera_id VARCHAR(50),
                camera_name VARCHAR(100),
                type VARCHAR(50),
                severity VARCHAR(50),
                details TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vlm_logs (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                camera_id VARCHAR(50),
                camera_name VARCHAR(100),
                severity VARCHAR(50),
                details TEXT
            )
        """)
        cur.execute("""
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
                vlm_description TEXT DEFAULT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gate_events (
                id SERIAL PRIMARY KEY,
                timestamp VARCHAR(50),
                event_type VARCHAR(50),
                leaflet_y REAL,
                leaflet_x REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at VARCHAR(50)
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                camera_id TEXT,
                camera_name TEXT,
                type TEXT,
                severity TEXT,
                details TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vlm_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                camera_id TEXT,
                camera_name TEXT,
                severity TEXT,
                details TEXT
            )
        """)
        cur.execute("""
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
                vlm_description TEXT DEFAULT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event_type TEXT,
                leaflet_y REAL,
                leaflet_x REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT
            )
        """)
    conn.commit()
    conn.close()

import bcrypt

def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_user(username, email, password):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed = get_password_hash(password)
    try:
        run_query(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email, hashed, timestamp),
            returning_id_field="id"
        )
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "integrity" in err_str or "duplicate" in err_str:
            return False
        raise e

def get_user(username):
    return run_query(
        "SELECT * FROM users WHERE username = ?",
        (username,),
        fetch_mode='one'
    )

def insert_system_log(camera_id, camera_name, event_type, severity, details):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_id = run_query(
        "INSERT INTO system_logs (timestamp, camera_id, camera_name, type, severity, details) VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), camera_name, event_type, severity, details),
        returning_id_field="id"
    )
    return {
        "id": last_id, "timestamp": timestamp, "camera_id": camera_id, 
        "camera_name": camera_name, "type": event_type, "severity": severity, "details": details
    }

def insert_vlm_log(camera_id, camera_name, severity, details):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_id = run_query(
        "INSERT INTO vlm_logs (timestamp, camera_id, camera_name, severity, details) VALUES (?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), camera_name, severity, details),
        returning_id_field="id"
    )
    return {
        "id": last_id, "timestamp": timestamp, "camera_id": camera_id, 
        "camera_name": camera_name, "severity": severity, "details": details
    }

def insert_alert_log(camera_id, camera_name, event_type, severity, details, evidence, vlm_status='PENDING', vlm_description=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_id = run_query(
        "INSERT INTO alert_logs (timestamp, camera_id, camera_name, type, severity, details, evidence, vlm_status, vlm_description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (timestamp, str(camera_id), camera_name, event_type, severity, details, evidence, vlm_status, vlm_description),
        returning_id_field="id"
    )
    return {
        "id": last_id, "timestamp": timestamp, "camera_id": camera_id, 
        "camera_name": camera_name, "type": event_type, "severity": severity, 
        "details": details, "evidence": evidence, "vlm_status": vlm_status, "vlm_description": vlm_description
    }

def update_alert_vlm(alert_id, vlm_status, vlm_description):
    run_query(
        "UPDATE alert_logs SET vlm_status = ?, vlm_description = ? WHERE id = ?",
        (vlm_status, vlm_description, alert_id)
    )
    return run_query(
        "SELECT * FROM alert_logs WHERE id = ?",
        (alert_id,),
        fetch_mode='one'
    )

def get_recent_system_logs(limit=200):
    return run_query(
        "SELECT * FROM system_logs WHERE camera_id NOT LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch_mode='all'
    )

def get_recent_test_system_logs(limit=200):
    return run_query(
        "SELECT * FROM system_logs WHERE camera_id LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch_mode='all'
    )

def get_recent_vlm_logs(limit=200):
    return run_query(
        "SELECT * FROM vlm_logs WHERE camera_id NOT LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch_mode='all'
    )

def get_recent_test_vlm_logs(limit=200):
    return run_query(
        "SELECT * FROM vlm_logs WHERE camera_id LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch_mode='all'
    )

def get_recent_alert_logs(limit=200):
    return run_query(
        "SELECT * FROM alert_logs ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch_mode='all'
    )

def get_recent_test_alert_logs(limit=200):
    return run_query(
        "SELECT * FROM alert_logs WHERE camera_id LIKE 'test_%' ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch_mode='all'
    )

def get_recent_gate_events(limit=200):
    raw_events = run_query("SELECT * FROM gate_events ORDER BY id DESC LIMIT 5000", fetch_mode='all')
    if not raw_events:
        return []
        
    hourly_groups = {}
    for ev in raw_events:
        ts = ev.get('timestamp')
        if not ts: continue
        hour_str = ts[:13] + ":00:00"
        
        if hour_str not in hourly_groups:
            hourly_groups[hour_str] = {"IN": 0, "OUT": 0, "timestamp": hour_str}
        
        etype = ev.get('event_type', 'IN')
        if etype in hourly_groups[hour_str]:
            hourly_groups[hour_str][etype] += 1
            
    aggregated_logs = []
    for i, hour in enumerate(sorted(hourly_groups.keys(), reverse=True)):
        if i >= limit:
            break
        counts = hourly_groups[hour]
        aggregated_logs.append({
            "id": i + 1,
            "timestamp": counts["timestamp"],
            "camera_name": "GATE CAM 3",
            "camera_id": "3",
            "event_type": "HOURLY",
            "severity": "INFO",
            "details": f"Hourly traffic summary: {counts['IN']} IN, {counts['OUT']} OUT."
        })
    return aggregated_logs

def insert_gate_event(event_type, leaflet_y, leaflet_x):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_query(
        "INSERT INTO gate_events (timestamp, event_type, leaflet_y, leaflet_x) VALUES (?, ?, ?, ?)",
        (timestamp, event_type, leaflet_y, leaflet_x)
    )

def delete_last_gate_event(event_type):
    run_query(
        "DELETE FROM gate_events WHERE id = (SELECT id FROM gate_events WHERE event_type = ? ORDER BY id DESC LIMIT 1)",
        (event_type,)
    )

def get_daily_gate_counts():
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    rows = run_query(
        "SELECT event_type, COUNT(*) as count FROM gate_events WHERE timestamp >= ? GROUP BY event_type",
        (cutoff,),
        fetch_mode='all'
    )
    counts = {"IN": 0, "OUT": 0}
    if rows:
        for row in rows:
            if row['event_type'] in counts:
                counts[row['event_type']] = row['count']
    return counts

def clear_system_logs(is_test=False):
    run_query("DELETE FROM system_logs")

def clear_vlm_logs(is_test=False):
    run_query("DELETE FROM vlm_logs")

def clear_alert_logs(is_test=False):
    run_query("DELETE FROM alert_logs")

def clear_gate_events():
    run_query("DELETE FROM gate_events")

# Initialize database
init_db()
