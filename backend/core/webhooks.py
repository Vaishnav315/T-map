import json
import logging
import requests
import threading
from typing import Dict, Any

from backend.core.database import run_query

logger = logging.getLogger(__name__)

def _fire_webhook_async(url: str, secret: str, payload: Dict[str, Any]):
    try:
        headers = {'Content-Type': 'application/json'}
        if secret:
            headers['X-SentinelIQ-Signature'] = secret
            
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code >= 400:
            logger.warning(f"[Webhook] Failed to deliver to {url}: {response.status_code} {response.text}")
        else:
            logger.info(f"[Webhook] Successfully delivered to {url}")
            
    except Exception as e:
        logger.error(f"[Webhook] Error delivering to {url}: {e}")


def dispatch_event(event_type: str, data: Dict[str, Any], tenant_id: str = "default"):
    """
    Looks up active webhooks for the tenant and fires them if they subscribe to this event.
    """
    try:
        webhooks = run_query(
            "SELECT * FROM webhooks WHERE tenant_id = ? AND is_active = 1",
            (tenant_id,),
            fetch_mode="all"
        )
        if not webhooks:
            return

        payload = {
            "event": event_type,
            "data": data
        }

        for wh in webhooks:
            try:
                events = json.loads(wh.get("event_types", "[]"))
            except:
                events = []

            # If no events specified, or event matches, fire
            if not events or event_type in events or "*" in events:
                # Fire asynchronously to avoid blocking the main thread
                threading.Thread(
                    target=_fire_webhook_async,
                    args=(wh["endpoint_url"], wh["secret"], payload),
                    daemon=True
                ).start()
    except Exception as e:
        logger.error(f"[Webhook] Error dispatching event: {e}")
