import React, { useState, useEffect } from 'react';
import './TestCenter.css';
import {
  Cpu, Square, Play, Activity, Video, Info,
  AlertTriangle, ShieldAlert, Layers, ShieldCheck,
  Terminal, Eye, Film, Sparkles, RefreshCw, Loader2, CheckCircle2
} from 'lucide-react';

const TEST_VIDEOS = [
  { id: 'gas_leak_panic',      name: 'Sudden Panic Attack',         filename: 'gas_leak_panic.mp4',      desc: 'Crowd panic and stampede (ST-GLAD).' },
  { id: 'perimeter_climb',     name: 'Perimeter Wall Climbing',     filename: 'perimeter_climb.mp4',     desc: 'Lone intruder wall climbing detection.' },
  { id: 'stglad_run',          name: 'Unexpected Running',          filename: 'stglad_run.mp4',          desc: 'Sudden running in quiet zone.' },
  { id: 'one_by_one',          name: 'One-By-One Gate Count',      filename: 'one_by_one.mp4',          desc: 'Gate counting & line crossing testing.' },
  { id: 'people_palace',       name: 'ByteTrack Palace',            filename: 'people_palace.mp4',       desc: 'Angled zone counting & vector tracking.' },
  { id: 'people_detection',    name: 'Intel General Tracking',      filename: 'people_detection.mp4',    desc: 'Pedestrian workforce tracking.' },
  { id: 'store_aisle',         name: 'Intel Store Aisle',           filename: 'store_aisle.mp4',         desc: 'Loitering, crowd anomaly, and idle monitoring.' },
  { id: 'fall',                name: 'Unified Fall Detection',      filename: 'fall.mp4',                desc: 'Posture tracking & fall safety alarms.' },
  { id: 'person_bicycle_car',  name: 'Street Traffic Flow',         filename: 'person_bicycle_car.mp4',  desc: 'Dynamic trajectory safety and ST-GLAD.' },
  { id: 'classroom',           name: 'Classroom Crowding',          filename: 'classroom.mp4',           desc: 'Dense student group interaction (ST-GLAD).' }
];

const AI_MODULES = [
  { id: 'people',       name: 'People Counting',       desc: 'Real-time worker density & tracking.',    color: 'mod-cyan',   accent: '#00e5ff' },
  { id: 'posture',      name: 'Fall Detection',         desc: 'Instant fall and collapse detection.',    color: 'mod-violet', accent: '#8b5cf6' },
  { id: 'stglad',       name: 'ST-GLAD (Graphs)',       desc: 'Spatial interaction & rapid chaos.',      color: 'mod-rose',   accent: '#f43f5e' },
  { id: 'perimeter',    name: 'Perimeter Wall Climbing', desc: 'Lone intruder wall scaling detection.', color: 'mod-orange', accent: '#f59e0b' },
  { id: 'intrusion',    name: 'Zone Intrusion',         desc: 'Unauthorized restricted area access.',    color: 'mod-rose',   accent: '#f43f5e' },
  { id: 'sliphazard',   name: 'Slip/Trip Hazard',       desc: 'Periodic scan for wet floors & obstacles.',color: 'mod-teal',   accent: '#14b8a6' }
];

const SEVERITY_META = {
  CRITICAL: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)',  icon: ShieldAlert,  label: 'CRITICAL' },
  HIGH:     { color: '#f97316', bg: 'rgba(249,115,22,0.12)', border: 'rgba(249,115,22,0.3)', icon: AlertTriangle, label: 'HIGH' },
  WARNING:  { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)', icon: AlertTriangle, label: 'WARNING' },
  INFO:     { color: '#00e5ff', bg: 'rgba(0,229,255,0.08)',  border: 'rgba(0,229,255,0.2)',  icon: Info,         label: 'INFO' },
  ERROR:    { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)',  icon: ShieldAlert,  label: 'ERROR' },
};

const getSeverityMeta = (sev) => SEVERITY_META[sev] || SEVERITY_META.INFO;

export default function TestCenter({ backendUrl }) {
  const [activeVideo, setActiveVideo] = useState(TEST_VIDEOS[0]);
  const [activeMods, setActiveMods]   = useState(new Set());
  const [running, setRunning]         = useState(false);
  const [feedVisible, setFeedVisible] = useState(false); // video stream visible independently of AI
  const [consoleTab, setConsoleTab]   = useState('alerts');

  const [alertLogs, setAlertLogs] = useState([]);
  const [sysLogs, setSysLogs]     = useState([]);
  const [vlmLogs, setVlmLogs]     = useState([]);

  // Fetch Test Logs
  const fetchTestLogs = async () => {
    try {
      const [alertRes, sysRes, vlmRes] = await Promise.all([
        fetch(`${backendUrl}/api/test_alert_logs`),
        fetch(`${backendUrl}/api/test_logs`),
        fetch(`${backendUrl}/api/test_vlm_logs`)
      ]);
      if (alertRes.ok) setAlertLogs(await alertRes.json());
      if (sysRes.ok)   setSysLogs(await sysRes.json());
      if (vlmRes.ok)   setVlmLogs(await vlmRes.json());
    } catch (e) {
      console.warn("Failed fetching test logs:", e);
    }
  };

  useEffect(() => {
    fetchTestLogs();
    const interval = setInterval(fetchTestLogs, 2000);
    return () => clearInterval(interval);
  }, [backendUrl]);

  // Hook into real-time SSE pushes
  useEffect(() => {
    window.onTestAlertReceived = (newAlert) => {
      if (newAlert.type === 'CLEAR_ALL') {
        setAlertLogs([]);
        return;
      }
      if (newAlert.camera_id === `test_${activeVideo.id}`) {
        setAlertLogs(prev => {
          if (newAlert.is_update) {
            // Find existing alert and update it instead of prepending
            const idx = prev.findIndex(a => a.id === newAlert.id);
            if (idx !== -1) {
              const nextState = [...prev];
              nextState[idx] = newAlert;
              return nextState;
            }
          }
          return [newAlert, ...prev].slice(0, 100);
        });
      }
    };
    return () => {
      window.onTestAlertReceived = null;
    };
  }, [activeVideo]);

  // Clear logs from DB
  const handleClearLogs = async (channel) => {
    if (channel === 'test_alert_logs') setAlertLogs([]);
    if (channel === 'test_logs')       setSysLogs([]);
    if (channel === 'test_vlm_logs')   setVlmLogs([]);
    try {
      await fetch(`${backendUrl}/api/${channel}/clear`, { method: 'POST' });
    } catch (e) {
      console.warn('Clear failed:', e);
    }
  };

  const handleToggleModule = (modId) => {
    setActiveMods(prev => {
      const updated = new Set(prev);
      if (updated.has(modId)) {
        updated.delete(modId);
      } else {
        updated.add(modId);
      }
      // If already running, send update start payload to backend immediately
      if (running) {
        updateBackendAnalytics(updated, activeVideo.id);
      }
      return updated;
    });
  };

  const updateBackendAnalytics = async (modulesSet, videoId) => {
    if (modulesSet.size === 0) {
      handleStop(videoId);
      return;
    }
    try {
      await fetch(`${backendUrl}/api/ai_analytics/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          modules: Array.from(modulesSet),
          cameras: [`test_${videoId}`]
        })
      });
    } catch (e) {
      console.error('Failed starting analytics:', e);
    }
  };

  const handleStart = () => {
    if (activeMods.size === 0) return;
    setRunning(true);
    setFeedVisible(true);
    updateBackendAnalytics(activeMods, activeVideo.id);
  };

  const handleStop = async (videoId = activeVideo.id) => {
    setRunning(false);
    // Keep feed visible after stop so user can still see the video
    try {
      await fetch(`${backendUrl}/api/ai_analytics/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cameras: [`test_${videoId}`] })
      });
    } catch (e) {
      console.error('Failed stopping analytics:', e);
    }
  };

  const handleVideoSelect = (video) => {
    if (running) handleStop(activeVideo.id);
    setActiveVideo(video);
    setRunning(false);
    setFeedVisible(false);
  };

  const handlePreviewFeed = () => {
    // Show raw video feed without AI (no bounding boxes)
    setFeedVisible(true);
  };

  return (
    <div className="test-center-container">

      <div className="tc-grid">
        {/* â”€â”€ COLUMN 1: SIDEBAR â”€â”€ */}
        <div className="tc-sidebar">
          {/* Card: Select Video */}
          <div className="tc-card">
            <h2 className="tc-card-title">
              <Film size={15} style={{ marginRight: 6 }} /> SELECT REFERENCE FEED
            </h2>
            <div className="tc-video-list">
              {TEST_VIDEOS.map(video => {
                const isActive = activeVideo.id === video.id;
                return (
                  <button
                    key={video.id}
                    className={`tc-video-btn ${isActive ? 'active' : ''}`}
                    onClick={() => handleVideoSelect(video)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span className="tc-video-btn-name">{video.name}</span>
                      <span className="tc-video-btn-file">{video.filename}</span>
                    </div>
                    <p className="tc-video-btn-desc">{video.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Card: Toggle Modules */}
          <div className="tc-card" style={{ marginTop: 16 }}>
            <h2 className="tc-card-title">
              <Cpu size={15} style={{ marginRight: 6 }} /> ENABLE AI MODULES
            </h2>
            <div className="tc-modules-grid">
              {AI_MODULES.map(mod => {
                const isSelected = activeMods.has(mod.id);
                return (
                  <button
                    key={mod.id}
                    className={`tc-mod-pill ${isSelected ? 'selected' : ''}`}
                    onClick={() => handleToggleModule(mod.id)}
                    style={{ '--mod-accent': mod.accent }}
                  >
                    <span className="tc-mod-pill-indicator" />
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                      <span className="tc-mod-pill-name">{mod.name}</span>
                      <span className="tc-mod-pill-desc">{mod.desc}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* â”€â”€ COLUMN 2: STREAM DISPLAY â”€â”€ */}
        <div className="tc-viewport-area">
          <div className="tc-viewport-card">
            <div className="tc-viewport-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="tc-live-dot" style={{ background: running ? '#10b981' : '#6b7280' }} />
                <span className="tc-viewport-title">{activeVideo.name}</span>
              </div>
              <span className="tc-viewport-cam-id">camera_id: test_{activeVideo.id}</span>
            </div>

            <div className="tc-stream-container">
              {feedVisible ? (
                <>
                  <img
                    key={activeVideo.id}
                    src={`${backendUrl}/video_feed/test_${activeVideo.id}?detect=${running}`}
                    alt="Test stream feed"
                    className="tc-stream-img"
                    onError={(e) => {
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                  <div className="tc-stream-fallback" style={{ display: 'none' }}>
                    <Video size={36} />
                    <span>Stream Error / Backend Offline</span>
                  </div>
                </>
              ) : (
                <div className="tc-stream-placeholder">
                  <Film size={48} className="tc-placeholder-icon" />
                  <h3>Feed Standby</h3>
                  <p>Click <strong>â–¶ Preview Feed</strong> to watch the video, or enable modules and click <strong>â–¶ Start AI</strong> to run detection.</p>
                </div>
              )}
            </div>

            <div className="tc-viewport-controls">
              {!feedVisible && (
                <button className="tc-ctrl-btn preview" onClick={handlePreviewFeed}>
                  <Eye size={14} /> Preview Feed
                </button>
              )}
              {feedVisible && !running && (
                <button
                  className="tc-ctrl-btn start"
                  onClick={handleStart}
                  disabled={activeMods.size === 0}
                >
                  <Play size={14} fill="#fff" /> Start AI Detection
                </button>
              )}
              {running && (
                <button className="tc-ctrl-btn stop" onClick={() => handleStop(activeVideo.id)}>
                  <Square size={14} fill="#fff" /> Stop AI
                </button>
              )}
              {feedVisible && (
                <button className="tc-ctrl-btn stop" style={{ background: 'rgba(107,114,128,0.2)', border: '1px solid rgba(107,114,128,0.4)' }}
                  onClick={() => { handleStop(activeVideo.id); setFeedVisible(false); }}>
                  <Square size={14} /> Close Feed
                </button>
              )}
            </div>
          </div>
        </div>

        {/* â”€â”€ COLUMN 3: TEST ALERTS TERMINAL â”€â”€ */}
        <div className="tc-console-area">
          <div className="tc-console-card">
            <div className="tc-console-tabs">
              <button
                className={`tc-console-tab ${consoleTab === 'alerts' ? 'active' : ''}`}
                onClick={() => setConsoleTab('alerts')}
              >
                <ShieldAlert size={14} /> TEST ALERTS ({alertLogs.length})
              </button>
              <button
                className={`tc-console-tab ${consoleTab === 'system' ? 'active' : ''}`}
                onClick={() => setConsoleTab('system')}
              >
                <Terminal size={14} /> TELEMETRY ({sysLogs.length})
              </button>
              <button
                className={`tc-console-tab ${consoleTab === 'vlm' ? 'active' : ''}`}
                onClick={() => setConsoleTab('vlm')}
              >
                <Sparkles size={14} /> VLM SCANS ({vlmLogs.length})
              </button>
              <button
                className="tc-console-tab tc-console-clear"
                title="Refresh logs"
                onClick={fetchTestLogs}
              >
                <RefreshCw size={12} />
              </button>
              {consoleTab === 'alerts' && alertLogs.length > 0 && (
                <button className="tc-console-tab tc-console-clear" onClick={() => handleClearLogs('test_alert_logs')} title="Clear test alerts">
                  ðŸ—‘ CLEAR
                </button>
              )}
              {consoleTab === 'system' && sysLogs.length > 0 && (
                <button className="tc-console-tab tc-console-clear" onClick={() => handleClearLogs('test_logs')} title="Clear test system logs">
                  ðŸ—‘ CLEAR
                </button>
              )}
              {consoleTab === 'vlm' && vlmLogs.length > 0 && (
                <button className="tc-console-tab tc-console-clear" onClick={() => handleClearLogs('test_vlm_logs')} title="Clear test VLM logs">
                  ðŸ—‘ CLEAR
                </button>
              )}
            </div>

            <div className="tc-console-body">
              {consoleTab === 'alerts' && (
                <div className="tc-log-timeline">
                  {alertLogs.length === 0 ? (
                    <div className="tc-empty-log">
                      <ShieldCheck size={32} color="#10b981" />
                      <p>No validation warnings triggered yet.</p>
                    </div>
                  ) : (
                    alertLogs.map((alert, i) => {
                      const vlmStatus = alert.vlm_status || 'VERIFIED';
                      const isCleared = vlmStatus === 'CLEARED';
                      const isPending = vlmStatus === 'PENDING';
                      const isVerified = vlmStatus === 'VERIFIED';

                      const meta = getSeverityMeta(alert.severity);
                      const Icon = meta.icon;
                      
                      let cardBorder = meta.border;
                      let cardBg = meta.bg;
                      let cardOpacity = 1;
                      
                      if (isCleared) {
                        cardBorder = 'rgba(156,163,175,0.2)';
                        cardBg = 'rgba(20,20,30,0.35)';
                        cardOpacity = 0.65;
                      } else if (isPending) {
                        cardBorder = 'rgba(59,130,246,0.35)';
                        cardBg = 'rgba(59,130,246,0.04)';
                      }

                      return (
                        <div
                          key={alert.id || i}
                          className="tc-alert-card"
                          style={{ 
                            borderColor: cardBorder, 
                            background: cardBg, 
                            opacity: cardOpacity,
                            transition: 'all 0.3s ease',
                            filter: isCleared ? 'grayscale(30%)' : 'none'
                          }}
                        >
                          <div className="tc-alert-header">
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <Icon size={14} color={isCleared ? '#9ca3af' : meta.color} />
                              <span style={{ color: isCleared ? '#9ca3af' : meta.color, fontWeight: 600 }}>{alert.type}</span>
                            </div>
                            
                            {/* AI Status Badge in Terminal */}
                            {isPending && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#3b82f6', fontSize: '9px', fontWeight: 'bold', animation: 'pulse-blue 1.5s infinite', marginLeft: 'auto', marginRight: '10px' }}>
                                  <Loader2 className="animate-spin" size={10} style={{ animation: 'spin 1.2s linear infinite' }} /> ANALYZING
                              </div>
                            )}
                            {isVerified && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#22c55e', fontSize: '9px', fontWeight: 'bold', marginLeft: 'auto', marginRight: '10px' }}>
                                  <CheckCircle2 size={10} /> VERIFIED
                              </div>
                            )}
                            {isCleared && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#9ca3af', fontSize: '9px', fontWeight: 'bold', marginLeft: 'auto', marginRight: '10px' }}>
                                  <CheckCircle2 size={10} /> CLEARED
                              </div>
                            )}
                            
                            <span className="tc-alert-time" style={{ marginLeft: isPending || isVerified || isCleared ? '0' : 'auto' }}>{alert.timestamp?.split(' ')[1] || alert.timestamp}</span>
                            <button 
                              className="tc-dismiss-alert-btn" 
                              onClick={() => setAlertLogs(prev => prev.filter(a => a.id !== alert.id))}
                              style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', marginLeft: '10px', fontSize: '14px' }}
                              title="Dismiss Alert"
                            >
                              âœ•
                            </button>
                          </div>
                          <p className="tc-alert-text" style={{ color: isCleared ? '#9ca3af' : undefined }}>
                            {alert.vlm_description || alert.details}
                          </p>
                          {alert.evidence && (
                            <div className="tc-alert-screenshot" style={{ opacity: isCleared ? 0.5 : 1 }}>
                              <img
                                src={`${backendUrl}/evidence/${alert.evidence}`}
                                alt="Alert evidence"
                                className="tc-screenshot-img"
                              />
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {consoleTab === 'system' && (
                <div className="tc-log-list">
                  {sysLogs.length === 0 ? (
                    <div className="tc-empty-log">
                      <Info size={28} />
                      <p>System telemetry logs empty.</p>
                    </div>
                  ) : (
                    sysLogs.map((log, i) => {
                      const meta = getSeverityMeta(log.severity);
                      return (
                        <div key={log.id || i} className="tc-sys-row" style={{ borderLeftColor: meta.color }}>
                          <span className="tc-sys-time">[{log.timestamp?.split(' ')[1] || log.timestamp}]</span>
                          <span className="tc-sys-cam">{log.camera_name}:</span>
                          <span className="tc-sys-desc">{log.details}</span>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {consoleTab === 'vlm' && (
                <div className="tc-log-list">
                  {vlmLogs.length === 0 ? (
                    <div className="tc-empty-log">
                      <Sparkles size={28} />
                      <p>VLM descriptions timeline empty.</p>
                    </div>
                  ) : (
                    vlmLogs.map((log, i) => (
                      <div key={log.id || i} className="tc-vlm-row">
                        <span className="tc-vlm-time">[{log.timestamp?.split(' ')[1] || log.timestamp}]</span>
                        <p className="tc-vlm-desc">{log.details}</p>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

