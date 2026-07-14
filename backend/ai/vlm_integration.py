"""
Slip/Trip Hazard Detection — WARNING severity.

Runs a periodic full-frame VLM scan every 90 seconds to detect
wet floors, spills, or trip hazards. The alert is NOT fired immediately —
it is only logged when the VLM confirms an actual hazard is present.

No evidence screenshot is generated (WARNING severity — policy: only HIGH/CRITICAL).
"""
import time
import re
import json
from typing import List
try:
    import ollama
except ImportError:
    ollama = None
import numpy as np

import asyncio
import threading
import cv2
from backend.core.state import add_vlm_log, add_alert_log

QWEN_MODEL = "qwen2.5vl:3b"
TRIAGE_MODEL = "llava:latest"

vlm_queue = None
vlm_loop = None
ollama_semaphore = None

import itertools
_task_counter = itertools.count()

_last_scan_times = {}

# How often to scan each camera (seconds)
SCAN_INTERVAL_SEC = 90.0


def detect_slip_hazard(camera_id: str, raw_frame: np.ndarray) -> List[dict]:
    """
    Periodically queues a full-frame VLM hazard scan.
    Only produces an alert if the VLM confirms a genuine hazard — 
    handled inside vlm_integration.py via the VLM prompt answer.
    """
    alerts = []
    now = time.time()

    last_scan = _last_scan_times.get(camera_id, 0)

    # Run once every SCAN_INTERVAL_SEC per camera
    if (now - last_scan) < SCAN_INTERVAL_SEC:
        return alerts

    _last_scan_times[camera_id] = now

    # We still emit the alert dict so the VLM cascade runs, but:
    #   - severity = "WARNING" → no screenshot will be saved (policy gate)
    #   - description is minimal — only written to DB if VLM confirms hazard
    alerts.append({
        "event_type": "SLIP_TRIP_HAZARD",
        "severity": "WARNING",
        "camera_id": camera_id,
        "track_id": None,
        "bbox": None,
        "description": "Periodic floor safety scan triggered.",
        "vlm_prompt": (
            "You are a safety inspector reviewing a factory/workplace floor camera. "
            "Look carefully at the floor and ground level only. "
            "Are there any wet floors, liquid spills, exposed cables, loose materials, "
            "or objects that pose a trip or slip hazard? "
            "If YES: describe the hazard in one sentence. "
            "If NO hazard is visible: respond with exactly 'NO HAZARD'."
        )
    })

    return alerts

def extract_json(text):
    text = text.strip()
    try:
        # Try to find a JSON block in the response
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return {"violation": True, "severity": "WARNING", "description": text}

async def call_ollama(model, prompt, image_bytes, options=None):
    """Sends API request to Ollama async client with permanent VRAM keep-alive lock."""
    if ollama is None:
        print("[VLM ERROR] Ollama not installed. Cannot call VLM.")
        return {"response": ""}
        
    async with ollama_semaphore:
        try:
            client = ollama.AsyncClient()
            response = await client.generate(
                model=model, prompt=prompt, images=[image_bytes], options=options or {}, keep_alive=-1
            )
            return response
        except Exception as e:
            print(f"[VLM CALL ERROR] Model {model} failed: {e}")
            return {"response": "", "error": str(e)}

async def process_vlm_task(camera_id, use_case, image_bytes, tid, prompt, alert_id=None):
    """The Diamond Cascade: Small VLM Triage -> Qwen 3B Ambiguity Resolver."""
    from config_loader import loader
    cam_info = loader.get_camera_details(camera_id)
    cam_name = cam_info.get("Name", f"Cam {camera_id}") if cam_info else f"Cam {camera_id}"

    try:
        if use_case == "RE_ID":
            print(f"[D-MCST RE-ID] Dispatching semantic signature extraction for Target #{tid} on Cam {camera_id}...")
            qwen_prompt = "Describe the person's clothing strictly as JSON. Keys must be EXACTLY: {\"top_color\": \"string\", \"bottom_color\": \"string\", \"is_uniform\": boolean}. Return ONLY the JSON."
            # We use Qwen directly for robust JSON structure parsing
            res_qw = await call_ollama(QWEN_MODEL, qwen_prompt, image_bytes)
            ans_qw = res_qw.get("response", "").strip()
            
            json_res = extract_json(ans_qw)
            
            from backend.core.reid_registry import global_reid_registry
            direction = prompt # the IN/OUT direction is passed through the prompt variable
            global_reid_registry.process_gate_crossing(camera_id, tid, direction, json.dumps(json_res))
            return

        # ── Special case: SLIP_TRIP_HAZARD — suppressed if VLM sees no hazard ──
        # For this use case, we skip Llava triage and go directly to Qwen
        # with a simple yes/no question. No score needed.
        if use_case == "SLIP_TRIP_HAZARD":
            slip_prompt = (
                f"{prompt} "
                "Answer with 'NO HAZARD' if the floor and ground level look safe. "
                "Otherwise, describe the hazard in one sentence starting with 'HAZARD:'"
            )
            res_slip = await call_ollama(TRIAGE_MODEL, slip_prompt, image_bytes,
                                         options={"num_predict": 30, "temperature": 0.0})
            ans_slip = res_slip.get("response", "").strip()
            if "NO HAZARD" in ans_slip.upper() or len(ans_slip) < 5:
                add_vlm_log(camera_id, cam_name, "INFO", f"[SLIP_TRIP_HAZARD | Clear] Floor scan: {ans_slip}")
                if alert_id is not None:
                    from backend.core.state import update_alert_log_vlm
                    update_alert_log_vlm(alert_id, "CLEARED", f"Cleared by AI Triage (No floor hazard detected: {ans_slip})")
                return
            # Genuine hazard found — log and alert
            add_vlm_log(camera_id, cam_name, "WARNING", f"[SLIP_TRIP_HAZARD | Confirmed] {ans_slip}")
            if alert_id is not None:
                from backend.core.state import update_alert_log_vlm
                update_alert_log_vlm(alert_id, "VERIFIED", f"[SLIP_TRIP_HAZARD Confirmed] {ans_slip}")
            else:
                add_alert_log(camera_id, cam_name, "SLIP_TRIP_HAZARD", "WARNING",
                              f"Floor hazard detected: {ans_slip}", vlm_status="VERIFIED")
            return

        # STEP 1: Small VLM Triage (Llava) using VQA description for high speed and descriptive alerts
        base_instruction = "You MUST start your response with the exact word '{keyword}' if {condition}, or 'NORMAL' if not. Then provide a concise description. IMPORTANT: Do not mention the 'red box' or 'colored line'. LIMIT YOUR DESCRIPTION TO EXACTLY 1 SHORT SENTENCE AND MAX 15 WORDS."
        
        if use_case == "SPATIAL_ANOMALY":
            md_prompt = f"You are a security AI analyzing a scene. {base_instruction.format(keyword='ANOMALY', condition='there is a crowd anomaly/panic')}"
        elif use_case == "FALL_DETECTED":
            md_prompt = f"You are a security AI analyzing a person. {base_instruction.format(keyword='FALLEN', condition='they have collapsed')}"
        elif use_case == "ZONE_INTRUSION":
            md_prompt = f"You are a security AI analyzing a person. {base_instruction.format(keyword='INTRUSION', condition='they are violating a zone')}"
        elif use_case == "PERIMETER_CLIMB":
            md_prompt = f"You are a security AI analyzing a person. {base_instruction.format(keyword='CLIMBING', condition='they are climbing a wall/fence')}"
        else:
            md_prompt = f"You are a security AI analyzing a scene. {base_instruction.format(keyword='VIOLATION', condition='it shows ' + prompt)}"

        res_md = await call_ollama(TRIAGE_MODEL, md_prompt, image_bytes, options={"temperature": 0.0, "num_predict": 80})
        ans_md = res_md.get("response", "").strip()
        
        print(f"[VLM DIAMOND CASCADE] Llava Raw Response for {use_case}: '{ans_md}'")
        
        ans_clean = ans_md.strip().upper().rstrip(".")
        
        if len(ans_clean) == 0:
            # Triage failed or returned empty; escalate to Qwen resolver to be safe
            score = 60
        else:
            is_normal = "NORMAL" in ans_clean
            is_anomaly = ("ANOMALY" in ans_clean or "FALLEN" in ans_clean or 
                          "INTRUSION" in ans_clean or "CLIMBING" in ans_clean or 
                          "VIOLATION" in ans_clean)
            
            if is_normal and not is_anomaly:
                # Llava confidently says NORMAL. Clear the alert.
                score = 0
            elif is_anomaly:
                # Llava is confident it's an anomaly. Bypass second step (Qwen).
                score = 100
            else:
                score = 60 # Ambiguous, escalate to Qwen resolver
                
        print(f"[VLM DIAMOND CASCADE] {use_case} on {camera_id} | Llava Resolved Score: {score}")

        if score < 50:
            # False Positive cleared by Triage. Zero heavy VLM compute used.
            add_vlm_log(camera_id, cam_name, "INFO", f"[{use_case} | Cleared by Triage] Score {score}. Not an anomaly (Triage: {ans_md}).")
            if alert_id is not None:
                from backend.core.state import update_alert_log_vlm
                update_alert_log_vlm(alert_id, "CLEARED", f"Cleared by AI Triage (Triage: {ans_md})")
            return

        if score >= 85:
            # Blatant Anomaly: Bypass Qwen directly to Alert Manager to save compute
            print(f"[VLM DIAMOND CASCADE] Score {score} >= 85. Blatant anomaly confirmed! Bypassing Qwen 3B.")
            if use_case in ["FALL_DETECTED", "SPATIAL_ANOMALY", "FIRE_SMOKE"]:
                severity = "CRITICAL"
            elif use_case in ["ZONE_INTRUSION", "UNATTENDED_OBJECT"]:
                severity = "HIGH"
            else:
                severity = "WARNING"
            
            # Clean up the keyword prefix from Llava's response for the UI
            clean_desc = ans_md
            for prefix in ["CLIMBING:", "CLIMBING", "ANOMALY:", "ANOMALY", "FALLEN:", "FALLEN", "INTRUSION:", "INTRUSION", "VIOLATION:", "VIOLATION"]:
                if clean_desc.upper().startswith(prefix):
                    clean_desc = clean_desc[len(prefix):].strip()
            
            description = clean_desc if clean_desc else "VLM Confirmed Alert"
            
            # Jump straight to alert logging
            add_vlm_log(camera_id, cam_name, severity, f"[{use_case} | Verified] {description}")
            trigger_ctx = f" [Target #{tid}]" if tid is not None else ""
            full_details = f"[{use_case} Alert]{trigger_ctx} {description}"
            if alert_id is not None:
                from backend.core.state import update_alert_log_vlm
                update_alert_log_vlm(alert_id, "VERIFIED", full_details)
            else:
                add_alert_log(camera_id, cam_name, use_case, severity, full_details, vlm_status="VERIFIED")
            return

        else:
            rule_injection = ""
            
        if use_case == "FALL_DETECTED":
            rule_injection += " RULE: If the subject has fallen or is lying on the ground, severity MUST be CRITICAL."
        elif use_case == "PERIMETER_CLIMB":
            rule_injection += " RULE: The security system has flagged this person as climbing a wall/fence. They are an INTRUDER. severity MUST be CRITICAL."
        elif use_case == "ZONE_INTRUSION":
            rule_injection += " RULE: If the subject is in a restricted area, severity MUST be HIGH."

        qwen_analysis_prompt = (
            f"Analyze the subject (highlighted by a RED BOX if present) in this security feed. "
            f"CRITICAL SYSTEM ALERT: A {use_case} event ({prompt}) was detected.\n{rule_injection}\n"
            "Act as an expert security analyst. Identify who the person might be (e.g., intruder, worker, security guard). "
            "IMPORTANT: In your description, DO NOT mention the 'red box' or the 'colored line'. Describe the facts of the scene in EXACTLY 1 short sentence, maximum 15 words, straight to the point. "
            "DO NOT explicitly state that it is a danger or a threat. Just describe the facts. "
            "Respond ONLY with a valid JSON object in this format: "
            '{"violation": true/false, "severity": "LOW"|"WARNING"|"HIGH"|"CRITICAL", "description": "concise analysis here"}'
        )
        res_qw = await call_ollama(QWEN_MODEL, qwen_analysis_prompt, image_bytes, options={"num_predict": 80, "temperature": 0.1})
        ans_qw = res_qw.get("response", "").strip()
        
        # Fallback if Qwen resolver is not installed (HTTP 404)
        if not ans_qw and "not found" in res_qw.get("error", "").lower():
            print("[VLM DIAMOND CASCADE] Qwen not found. Falling back to Triage's original response.")
            ans_qw = ans_md
            
        print(f"[VLM DIAMOND CASCADE] Qwen 3B Resolved Answer: '{ans_qw}'")
        
        is_qw_no = (
            ans_qw.upper() == "NO" or 
            ans_qw.upper().startswith("NO,") or 
            ans_qw.upper().startswith("NO ") or
            "NO ANOMALY" in ans_qw.upper()
        )
        
        json_res = extract_json(ans_qw)
        if not json_res.get("violation", False):
            add_vlm_log(camera_id, cam_name, "INFO", f"[{use_case} | Cleared by Qwen] {json_res.get('description', '')}")
            if alert_id is not None:
                from backend.core.state import update_alert_log_vlm
                update_alert_log_vlm(alert_id, "CLEARED", f"Cleared by AI Verification: {json_res.get('description', 'Not an anomaly')}")
            return

        raw_sev = json_res.get("severity", "WARNING").upper()
        if raw_sev not in {"LOW", "WARNING", "HIGH", "CRITICAL"}:
            raw_sev = "WARNING"
        severity = raw_sev
        description = json_res.get("description", ans_qw)

        # Log to VLM channel for VLM Scans timeline
        add_vlm_log(camera_id, cam_name, severity, f"[{use_case} | Verified] {description}")

        # FINAL ALERT MANAGER EXECUTION
        # if tid is not None:
        #     trigger_highlight(camera_id, tid, 5.0)

        trigger_ctx = f" [Target #{tid}]" if tid is not None else ""
        full_details = f"[{use_case} Alert]{trigger_ctx} {description}"

        if alert_id is not None:
            from backend.core.state import update_alert_log_vlm
            update_alert_log_vlm(alert_id, "VERIFIED", full_details)
        else:
            add_alert_log(camera_id, cam_name, use_case, severity, full_details, vlm_status="VERIFIED")

    except Exception as e:
        print(f"[VLM PIPELINE ERROR] Camera {camera_id} use_case {use_case}: {e}")

def clear_vlm_queue():
    """Safely clears all pending tasks from the VLM priority queue."""
    if vlm_queue is not None:
        try:
            while not vlm_queue.empty():
                vlm_queue.get_nowait()
        except:
            pass

def enqueue_vlm_task(camera_id, use_case, frame, box, tid, prompt, severity="WARNING", alert_id=None, track_history=None):
    """Enqueues VLM analysis task to run inside the priority worker queue thread-safely."""
    try:
        target_frame = frame.copy()
        
        if box is not None:
            x1, y1, x2, y2 = map(int, box)
            
            # --- IVF (Inference Value Function) Filter ---
            if tid is not None:
                from backend.ai.modules.ra_aac import evaluate_ivf
                crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
                should_process, ivf_score = evaluate_ivf(camera_id, tid, use_case, crop)
                if not should_process:
                    print(f"[IVF FILTER] Dropped redundant frame for Target #{tid} on {camera_id} (Score: {ivf_score:.2f}) before VLM.")
                    if alert_id is not None:
                        from backend.core.state import update_alert_log_vlm
                        update_alert_log_vlm(alert_id, "VERIFIED", "Skipped VLM verification due to visual redundancy (target profile matches active baseline).")
                    return  # Skip task: visually redundant/insufficient change
                else:
                    print(f"[IVF FILTER] Passed frame for Target #{tid} on {camera_id} (Score: {ivf_score:.2f}) to VLM.")
            
            cv2.rectangle(target_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)

        # --- Visual Temporal Features (Motion Trail) ---
        if track_history and len(track_history) >= 2:
            for i in range(1, len(track_history)):
                b1 = track_history[i-1]
                b2 = track_history[i]
                c1 = (int((b1[0] + b1[2]) / 2), int((b1[1] + b1[3]) / 2))
                c2 = (int((b2[0] + b2[2]) / 2), int((b2[1] + b2[3]) / 2))
                # Fade color from yellow (old) to red (new) to show direction
                ratio = i / float(len(track_history))
                color = (0, int(255 * (1 - ratio)), 255) # BGR: Yellow (0,255,255) -> Red (0,0,255)
                cv2.line(target_frame, c1, c2, color, 3)
            
            prompt += " (Note: A visual colored line from yellow to red indicates the person's recent motion path over the last few seconds.)"
            
        cv2.imwrite("vlm_debug.jpg", target_frame)
            
        _, buffer = cv2.imencode(".jpg", target_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        image_bytes = buffer.tobytes()

        if vlm_queue is None:
            print("[VLM PIPELINE WARNING] Priority queue not initialized yet. Skipping task.")
            return

        if severity in ["CRITICAL", "HIGH"]:
            priority = 0
        elif severity == "WARNING":
            priority = 1
        else:
            priority = 2

        task_data = (camera_id, use_case, image_bytes, tid, prompt, alert_id)
        vlm_loop.call_soon_threadsafe(vlm_queue.put_nowait, (priority, next(_task_counter), task_data))
    except Exception as e:
        print(f"[VLM QUEUE ERROR]: {e}")

async def _vlm_worker():
    global vlm_queue
    while True:
        try:
            priority, count, task_data = await vlm_queue.get()
            camera_id, use_case, image_bytes, tid, prompt, alert_id = task_data
            await process_vlm_task(camera_id, use_case, image_bytes, tid, prompt, alert_id)
            vlm_queue.task_done()
        except Exception as e:
            print(f"[VLM WORKER ERROR]: {e}")

def _run_vlm_thread():
    global vlm_loop, vlm_queue, ollama_semaphore
    vlm_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(vlm_loop)
    vlm_queue = asyncio.PriorityQueue()
    ollama_semaphore = asyncio.Semaphore(1)
    vlm_loop.create_task(_vlm_worker())
    vlm_loop.run_forever()

def start_vlm_worker():
    t = threading.Thread(target=_run_vlm_thread, daemon=True)
    t.start()
