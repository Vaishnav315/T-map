import cv2
import numpy as np
import time

# Cache: "camera_id_use_case_tid" -> {"crop": img, "timestamp": time.time()}
_vlm_eval_cache = {}

def fast_mse_similarity(img1, img2):
    """
    Computes a fast structural similarity between two crops.
    Returns 1.0 for identical images, down to 0.0 for completely different images.
    """
    if img1 is None or img2 is None or img1.size == 0 or img2.size == 0:
        return 0.0
        
    # Resize to 64x64 to remove minor jitter/noise and speed up compute
    i1 = cv2.resize(cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32)
    i2 = cv2.resize(cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32)
    
    mse = np.mean((i1 - i2) ** 2)
    # Convert MSE to similarity score (0 to 1). Max MSE for 8-bit is 255^2 = 65025
    sim = max(0.0, 1.0 - (mse / 10000.0))  # Tuned denominator: an MSE of 10k is practically completely different
    return sim

def compute_visual_entropy(img):
    """
    Computes Shannon entropy of the image histogram.
    High entropy implies high visual detail, movement, or complex posture changes.
    """
    if img is None or img.size == 0:
        return 0.0
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist / (hist.sum() + 1e-7)
    
    # Calculate Shannon Entropy
    entropy = -np.sum(hist * np.log2(hist + 1e-7))
    # Normalize (max entropy for 8-bit grayscale is 8.0)
    return min(1.0, entropy / 8.0)

def evaluate_ivf(camera_id, tid, use_case, current_crop):
    """
    Inference Value Function (IVF).
    Determines if a frame warrants heavy VLM processing.
    Returns: (bool should_process, float score)
    """
    cache_key = f"{camera_id}_{use_case}_{tid}"
    now = time.time()
    
    # Always process the first time
    if cache_key not in _vlm_eval_cache:
        _vlm_eval_cache[cache_key] = {"crop": current_crop, "timestamp": now}
        return True, 1.0
        
    cached = _vlm_eval_cache[cache_key]
    last_crop = cached["crop"]
    last_time = cached["timestamp"]
    
    # If it's been more than 30 seconds since the last VLM eval, force an update
    if now - last_time > 30.0:
        _vlm_eval_cache[cache_key] = {"crop": current_crop, "timestamp": now}
        return True, 1.0
        
    # Calculate similarity and entropy
    similarity = fast_mse_similarity(last_crop, current_crop)
    entropy = compute_visual_entropy(current_crop)
    
    # Inference Value Function formulation
    # High entropy (chaos) increases value. High similarity decreases value.
    w_e = 0.4
    w_s = 0.6
    
    # V_I(t) = w_e * Entropy + w_s * (1 - Similarity)
    v_i = (w_e * entropy) + (w_s * (1.0 - similarity))
    
    threshold = 0.35 # If change/chaos is less than 35%, skip VLM
    
    should_process = v_i >= threshold
    
    if should_process:
        _vlm_eval_cache[cache_key] = {"crop": current_crop, "timestamp": now}
        
    return should_process, v_i
