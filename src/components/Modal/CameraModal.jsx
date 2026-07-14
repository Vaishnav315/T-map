import React, { useState, useEffect, useRef } from 'react';
import { Shield, Users, Zap, Eye, Minimize2, Maximize2, X, AlertTriangle, Wifi, Activity } from 'lucide-react';

/* â”€â”€â”€ AI Mock Inference Hook â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function initializeAIInferenceStream(deviceId, _videoEl, onAlert) {
  const threats = [
    'Unidentified Intrusion: Perimeter Zone D Breach',
    'Worker Safety Violation: PPE Helmet Missing',
    'Hazardous Obstruction: Logistics Path Blocked',
    'Heat Signature Anomaly: Unit-1 Panel Overheating',
  ];
  const interval = setInterval(() => {
    if (Math.random() < 0.08) {
      onAlert({
        id: Date.now(),
        timestamp: new Date().toLocaleTimeString('en-GB'),
        camera_id: deviceId,
        type: 'AI_CV_ALERT',
        severity: 'WARNING',
        details: threats[Math.floor(Math.random() * threats.length)],
      });
    }
  }, 10000);
  return () => clearInterval(interval);
}

/* â”€â”€â”€ Main Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
export default function CameraModal({
  activeCamera, handleCloseCamera,
  isMaximized, setIsMaximized,
  detectFacesActive, setDetectFacesActive,
  backendUrl, isBackendOffline,
  stats, accent, satelliteAccent,
  setSelectedWorkerId, selectedWorkerId,
  isTrackingOnDashboard,
}) {


  const [webrtcFailed, setWebrtcFailed]   = useState(true); // Default to true for instant MJPEG load
  const [aiAlertActive, setAiAlertActive] = useState(false);
  const [aiAlertMsg, setAiAlertMsg]       = useState('');
  const [imgLoaded, setImgLoaded]         = useState(false);
  const [imgError, setImgError]           = useState(false);

  const videoRef = useRef(null);
  const pcRef    = useRef(null);

  /* Resolve live stat for this camera */
  let liveStat = { person_count: 0 };
  if (activeCamera) {
    if (Array.isArray(stats?.cameras))
      liveStat = stats.cameras.find(c => String(c.id) === String(activeCamera.id)) || liveStat;
    else if (stats?.cameras?.[activeCamera.id])
      liveStat = stats.cameras[activeCamera.id];
  }

  /* â”€â”€ WebRTC / MJPEG stream setup â”€â”€ */
  useEffect(() => {
    if (!activeCamera) return;
    
    // Always use MJPEG for instant loading (skip WebRTC timeout lag)
    setWebrtcFailed(true); 
    setImgLoaded(false);
    setImgError(false);
    setAiAlertActive(false);
    let active = true;

    // Toggle backend AI tracking based on detectFacesActive
    if (detectFacesActive) {
      fetch(`${backendUrl}/api/map_tracking/${activeCamera.id}/on`, { method: 'POST' }).catch(() => {});
    }

    let cleanupAI = null;
    if (detectFacesActive) {
      cleanupAI = initializeAIInferenceStream(activeCamera.id, videoRef.current, (alert) => {
        if (!active) return;
        setAiAlertActive(true);
        setAiAlertMsg(alert.details);
        setTimeout(() => { if (active) setAiAlertActive(false); }, 4000);
      });
    }

    return () => {
      active = false;
      if (cleanupAI) cleanupAI();
      
      // Stop background tracking if closed/disabled and dashboard tracking is not active
      if (!isTrackingOnDashboard) {
        fetch(`${backendUrl}/api/map_tracking/${activeCamera.id}/off`, { method: 'POST' }).catch(() => {});
      }
    };
  }, [activeCamera, detectFacesActive, backendUrl, isTrackingOnDashboard]);

  /* MJPEG fallback URL â€” always point to Flask backend proxy */
  const mjpegUrl = activeCamera ? `${backendUrl}/video_feed/${activeCamera.id}?detect=${detectFacesActive}&selected_worker=${selectedWorkerId || ''}` : '';

  /* Click-to-select worker in video */
  const handleVideoClick = async (e) => {
    if (!activeCamera) return;
    const rect = e.target.getBoundingClientRect();
    const xNorm = (e.clientX - rect.left) / rect.width;
    const yNorm = (e.clientY - rect.top)  / rect.height;
    try {
      const res = await fetch(`${backendUrl}/api/click_video/${activeCamera.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x: xNorm, y: yNorm }),
      });
      const data = await res.json();
      if (data.success && data.worker_id !== -1)
        setSelectedWorkerId(data.worker_id);
    } catch { /* silent */ }
  };

  const liveCount = isBackendOffline ? 0 : (liveStat?.person_count || 0);

  if (!activeCamera) return null;

  return (
    <div className="modal-backdrop" onClick={handleCloseCamera}>
      <div
        className={`modal-container ${isMaximized ? 'maximized' : ''}`}
        onClick={e => e.stopPropagation()}
        style={aiAlertActive ? { border: '1px solid rgba(239,68,68,0.6)', boxShadow: '0 0 40px rgba(239,68,68,0.3)' } : {}}
      >

        {/* â”€â”€ HEADER â”€â”€ */}
        <div className="modal-header" style={{ flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 auto", minWidth: 200 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: 'var(--text-main)' }}>
              {activeCamera.name}
            </h3>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              {webrtcFailed ? 'MJPEG PROXY FEED' : 'WebRTC WHEP'} &nbsp;Â·&nbsp; ID {activeCamera.id} &nbsp;Â·&nbsp; {activeCamera.ip}
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            {activeCamera && (activeCamera.name?.toUpperCase().includes('SECURITY') || activeCamera.area?.toUpperCase().includes('SECURITY') || activeCamera.area?.toUpperCase().includes('PERIMETER')) && (
              <div style={{ display: 'flex', gap: 4, fontSize: 9, fontWeight: 'bold', alignItems: 'center', marginRight: 10 }}>
                <span style={{ color: '#10b981', background: 'rgba(16,185,129,0.12)', padding: '2px 4px',  border: '1px solid rgba(16,185,129,0.3)' }}>
                  IN {liveStat?.gate_in || 0}
                </span>
                <span style={{ color: '#f87171', background: 'rgba(239,68,68,0.12)', padding: '2px 4px',  border: '1px solid rgba(239,68,68,0.3)' }}>
                  OUT {liveStat?.gate_out || 0}
                </span>
              </div>
            )}
            <label
              className={`modal-ai-toggle ${detectFacesActive ? 'on' : 'off'}`}
              title="Toggle AI Analytics"
            >
              <input
                type="checkbox"
                checked={detectFacesActive}
                onChange={e => {
                  const val = e.target.checked;
                  setDetectFacesActive(val);
                  if (!val && !isTrackingOnDashboard) {
                    fetch(`${backendUrl}/api/map_tracking/${activeCamera.id}/off`, { method: 'POST' }).catch(() => {});
                  }
                }}
              />
              <Eye size={13} />
              {detectFacesActive ? 'AI ACTIVE' : 'ENABLE AI'}
            </label>

            <button className="btn btn-outline" style={{ padding: '4px' }} onClick={() => setIsMaximized(v => !v)} title="Toggle maximize">
              {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button className="btn btn-outline" style={{ padding: '4px', borderColor: 'transparent' }} onClick={handleCloseCamera} title="Close">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* â”€â”€ AI ALERT BANNER â”€â”€ */}
        {aiAlertActive && (
          <div className="modal-alert-banner">
            <AlertTriangle size={14} />
            âš  AI ANOMALY DETECTED â€” {aiAlertMsg}
          </div>
        )}

        {/* â”€â”€ BODY â”€â”€ */}
        <div className="modal-body" style={{ flexDirection: 'column' }}>
          {/* Info bar */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: '8px 16px', background: 'var(--bg-card)', borderBottom: '1px solid var(--border)' }}>
            <div className="tag tag-muted">
              {webrtcFailed
                ? <><Wifi size={12} /> ENCRYPTED MJPEG</>
                : <><Shield size={12} /> LOW-LATENCY WEBRTC</>}
            </div>
            <div className="tag tag-cyan">
              <Users size={12} />
              LIVE COUNT: {liveCount}
            </div>
            {detectFacesActive && (
              <div className="tag tag-accent">
                <Zap size={12} />
                BYTETRACK + AI INTERCEPTOR
              </div>
            )}
          </div>

          {/* Video */}
          <div
            style={aiAlertActive ? { border: '2px solid var(--danger)', flex: 1, position: 'relative' } : { flex: 1, position: 'relative', background: '#000' }}
          >
            {/* WebRTC video element */}
            {(!webrtcFailed && !detectFacesActive) && (
              <video
                key={activeCamera.id}
                ref={videoRef}
                autoPlay playsInline muted
                onClick={handleVideoClick}
                style={{
                  width: '100%', height: 'auto',
                  display: 'block', cursor: 'crosshair',
                }}
              />
            )}

            {/* MJPEG fallback - Force MJPEG if AI is enabled to see the bounding boxes */}
            {(webrtcFailed || detectFacesActive) && (
              <>
                {!imgError ? (
                  <img
                    key={`${activeCamera.id}_${detectFacesActive}_${selectedWorkerId}`}
                    src={mjpegUrl}
                    alt="TASL Camera Stream"
                    onClick={handleVideoClick}
                    onLoad={() => { setImgLoaded(true); setImgError(false); }}
                    onError={() => setImgError(true)}
                    style={{ width: '100%', height: 'auto', display: 'block', cursor: 'crosshair' }}
                  />
                ) : (
                  /* Graceful offline placeholder */
                  <div style={{
                    width: '100%', height: '100%', minHeight: 300,
                    display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center',
                    gap: 14, color: 'var(--text-3)', fontFamily: 'var(--mono)', fontSize: 12,
                    background: 'rgba(6,10,18,0.95)',
                  }}>
                    <div style={{
                      width: 60, height: 60, borderRadius: '50%',
                      background: 'rgba(239,68,68,0.08)',
                      border: '1px solid rgba(239,68,68,0.2)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Activity size={24} color="var(--red)" style={{ opacity: 0.6 }} />
                    </div>
                    <span>CAMERA OFFLINE / CONNECTINGâ€¦</span>
                    <span style={{ fontSize: 10, opacity: 0.5 }}>
                      {activeCamera.ip} &nbsp;Â·&nbsp; RTSP Stream Unavailable
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
