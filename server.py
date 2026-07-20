"""
SentinelIQ AI Safety Platform — Production Server Launcher
=====================================================
Run with:
  python server.py

Or for Docker / production:
  uvicorn backend.core.app:app --host 0.0.0.0 --port 5000 --workers 1

NOTE: workers=1 is intentional — the frame-buffer state lives in-process.
      Use nginx in front for load balancing at the HTTP level.
"""

import os
import sys
from pathlib import Path

# ── Load .env file (if present) ───────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[SentinelIQ] Loaded environment from: {env_path}")
    else:
        # Graceful fallback — try .env in cwd
        cwd_env = Path.cwd() / ".env"
        if cwd_env.exists():
            load_dotenv(cwd_env)
            print(f"[SentinelIQ] Loaded environment from: {cwd_env}")
        else:
            print(
                "[SentinelIQ WARNING] No .env file found.\n"
                "  Copy .env.example to .env and fill in your secrets.\n"
                "  Run: cp .env.example .env"
            )
except ImportError:
    print("[SentinelIQ WARNING] python-dotenv not installed. Install with: pip install python-dotenv")

# ── Configuration ─────────────────────────────────────────────────────────────
HOST    = os.getenv("HOST", "0.0.0.0")
PORT    = int(os.getenv("PORT", "5001"))
TLS     = os.getenv("TLS_ENABLED", "false").lower() == "true"
CERT    = os.getenv("TLS_CERT_FILE", "auto.crt")
KEY_F   = os.getenv("TLS_KEY_FILE",  "auto.key")

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("[SentinelIQ ERROR] uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    print("=" * 60)
    print("  🛡️  SentinelIQ AI Safety Platform")
    print("  Starting server...")
    print("=" * 60)
    print(f"  Host   : {HOST}:{PORT}")
    print(f"  TLS    : {'✅ Enabled' if TLS else '❌ Disabled (development mode)'}")
    print(f"  Docs   : http{'s' if TLS else ''}://{HOST if HOST != '0.0.0.0' else 'localhost'}:{PORT}/api/docs")
    print("=" * 60)

    uvicorn_config = dict(
        app="backend.core.app:app",
        host=HOST,
        port=PORT,
        workers=1,           # DO NOT increase — frame-buffer state is in-process
        reload=False,        # DO NOT enable — kills camera streaming threads
        access_log=True,
        timeout_keep_alive=75,
        loop="asyncio",
    )

    if TLS:
        cert_path = Path(CERT)
        key_path  = Path(KEY_F)

        if not cert_path.exists() or not key_path.exists():
            print(
                f"[SentinelIQ TLS ERROR] TLS_ENABLED=true but cert/key files not found:\n"
                f"  cert: {cert_path.resolve()}\n"
                f"  key:  {key_path.resolve()}\n\n"
                "Generate self-signed certs for testing:\n"
                "  openssl req -x509 -newkey rsa:4096 -keyout auto.key -out auto.crt "
                "-days 365 -nodes -subj '/CN=localhost'"
            )
            sys.exit(1)

        uvicorn_config["ssl_certfile"] = str(cert_path)
        uvicorn_config["ssl_keyfile"]  = str(key_path)
        print(f"[SentinelIQ] TLS enabled with cert: {cert_path}")

    uvicorn.run(**uvicorn_config)
