import React, { useState, useEffect } from 'react';
import {
  Cpu, Square, Play, Activity, Video, Search, Trash2,
  AlertTriangle, ShieldAlert, ShieldCheck, Info,
  CheckCircle2, Crosshair
} from 'lucide-react';

const BACKEND = 'http://127.0.0.1:5001';

const MODS = [
  { id: 'people',       name: 'People Counting',      desc: 'Real-time worker density & tracking.',    accent: '#0EA5E9', engine: 'YOLO' },
  { id: 'posture',      name: 'Fall Detection',       desc: 'Instant fall and collapse detection.',    accent: '#8B5CF6', engine: 'YOLO+Cascade' },
  { id: 'stglad',       name: 'ST-GLAD (Graphs)',     desc: 'Spatial interaction & rapid chaos detection.', accent: '#F43F5E', engine: 'Math/Laplacian' },
  { id: 'perimeter',    name: 'Perimeter Wall Climbing', desc: 'Lone intruder wall scaling detection.', accent: '#F59E0B', engine: 'Spatial Rules' },
  { id: 'intrusion',    name: 'Zone Intrusion',       desc: 'Unauthorized restricted area access.',    accent: '#F43F5E', engine: 'YOLO+Cascade' },
  { id: 'sliphazard',   name: 'Slip/Trip Hazard',     desc: 'Periodic scan for wet floors & obstacles.',accent: '#10B981', engine: 'VLM Scan' },
];

const SEVERITY_META = {
  CRITICAL: { color: 'var(--danger)', bg: 'var(--bg-surface)', icon: ShieldAlert,  label: 'CRITICAL' },
  HIGH:     { color: 'var(--warning)', bg: 'var(--bg-surface)', icon: AlertTriangle, label: 'HIGH' },
  WARNING:  { color: 'var(--warning)', bg: 'var(--bg-surface)', icon: AlertTriangle, label: 'WARNING' },
  INFO:     { color: 'var(--info)',    bg: 'var(--bg-surface)', icon: Info,         label: 'INFO' },
  ERROR:    { color: 'var(--danger)', bg: 'var(--bg-surface)', icon: ShieldAlert,  label: 'ERROR' },
};

const getSeverityMeta = (sev) => SEVERITY_META[sev] || SEVERITY_META.INFO;

const CamGridCell = ({ cam, isTracking, onExpand, isExpanded, onRemove, backendUrl }) => (
  <div style={{ background: '#000', position: 'relative', border: `2px solid \${isTracking ? 'var(--accent)' : 'var(--border)'}`, minHeight: 180, height: '100%', display: 'flex', flexDirection: 'column' }}>
    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, padding: '8px 12px', background: 'linear-gradient(rgba(0,0,0,0.8), transparent)', display: 'flex', justifyContent: 'space-between', zIndex: 10 }}>
      <span style={{ color: '#FFF', fontSize: 11, fontWeight: 800, fontFamily: 'var(--mono)' }}>{cam.name}</span>
      <div style={{ display:'flex', gap:4 }}>
        <button className="btn btn-outline" style={{ padding: '2px 6px', fontSize: 10, borderColor: 'rgba(255,255,255,0.2)', color: '#FFF', background: 'transparent' }} onClick={(e) => { e.stopPropagation(); onExpand(cam.id); }}>
          {isExpanded ? '⊠' : '⊞'}
        </button>
        <button className="btn btn-danger" style={{ padding: '2px 6px', fontSize: 10 }} onClick={(e) => { e.stopPropagation(); onRemove(cam.id); }}>✖</button>
      </div>
    </div>
    
    <img
      src={`\${backendUrl}/video_feed/\${cam.id}?detect=\${isTracking}`}
      alt={cam.name}
      style={{ width: '100%', height: '100%', objectFit: 'contain', flex: 1 }}
      onError={(e) => { e.target.style.display='none'; e.target.nextSibling.style.display='flex'; }}
    />
    <div className="empty-state" style={{ display: 'none' }}>
      <Video size={24} style={{ opacity:0.3, color: '#FFF' }}/> 
      <span style={{ color: '#FFF' }}>Feed Unavailable</span>
    </div>

    <div style={{ position: 'absolute', bottom: 8, right: 8, display: 'flex', gap: 6, zIndex: 10 }}>
      <span style={{ background: 'rgba(0,0,0,0.6)', color: '#FFF', padding: '2px 6px', fontSize: 10, fontFamily: 'var(--mono)', border: '1px solid rgba(255,255,255,0.2)' }}>#{cam.id}</span>
      {isTracking && <span style={{ background: 'var(--accent)', color: '#FFF', padding: '2px 6px', fontSize: 10, fontWeight: 800, fontFamily: 'var(--mono)' }}>● AI LIVE</span>}
    </div>
  </div>
);

const LogRow = ({ entry }) => {
  const meta = getSeverityMeta(entry.severity);
  const SevIcon = meta.icon;
  return (
    <div style={{ display: 'flex', gap: 12, padding: '12px 16px', borderBottom: '1px solid var(--border-light)', background: meta.bg }}>
      <SevIcon size={16} color={meta.color} style={{ flexShrink: 0, marginTop: 2 }} />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-muted)' }}>{entry.timestamp?.split(' ')[1] || entry.timestamp}</span>
          <span className="tag" style={{ borderColor: meta.color, color: meta.color }}>{meta.label}</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 700, color: 'var(--text-main)' }}>{entry.camera_name || `CAM-\${entry.camera_id}`}</span>
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-body)' }}>{entry.details}</div>
      </div>
    </div>
  );
};

const AlertRow = ({ entry, backendUrl }) => {
  const meta = getSeverityMeta(entry.severity);
  const SevIcon = meta.icon;
  const hasEvidence = entry.evidence && entry.evidence !== "";
  const isPending = entry.vlm_status === 'PENDING';
  const isVerified = entry.vlm_status === 'VERIFIED';
  const isCleared = entry.vlm_status === 'CLEARED';
  
  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column',
      gap: 8, 
      padding: '16px', 
      borderBottom: '1px solid var(--border-light)', 
      background: 'var(--bg-card)',
      borderLeft: `3px solid \${meta.color}`
    }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <SevIcon size={16} color={meta.color} style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              {entry.timestamp?.split(' ')[1] || entry.timestamp}
            </span>
            <span className="tag" style={{ background: 'transparent', borderColor: meta.color, color: meta.color, fontSize: 9, padding: '1px 4px' }}>
              {meta.label}
            </span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 700, color: 'var(--text-main)' }}>
              {entry.camera_name || `CAM-\${entry.camera_id}`}
            </span>
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-main)', marginBottom: 2 }}>
            {entry.type}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-body)', lineHeight: '1.4' }}>
            {entry.details}
          </div>
        </div>
      </div>
      
      {entry.vlm_status && (
        <div style={{ 
          marginTop: 4, 
          padding: '6px 10px', 
          fontSize: 10, 
          background: isPending ? 'rgba(245, 158, 11, 0.08)' : isVerified ? 'rgba(16, 185, 129, 0.08)' : 'rgba(107, 114, 128, 0.08)',
          border: `1px solid \${isPending ? 'rgba(245, 158, 11, 0.2)' : isVerified ? 'rgba(16, 185, 129, 0.2)' : 'rgba(107, 114, 128, 0.2)'}`,
          color: isPending ? 'var(--warning)' : isVerified ? 'var(--accent)' : 'var(--text-muted)',
          display: 'flex',
          flexDirection: 'column',
          gap: 2
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 9, textTransform: 'uppercase' }}>
            <span style={{ 
              width: 6, 
              height: 6, 
               
              background: isPending ? 'var(--warning)' : isVerified ? 'var(--accent)' : 'var(--text-muted)'
            }} />
            {isPending ? 'Awaiting AI Verification' : isVerified ? 'AI Verified' : 'Cleared by AI'}
          </div>
          {entry.vlm_description && (
            <div style={{ fontSize: 11, color: 'var(--text-body)', marginTop: 2, fontStyle: 'italic' }}>
              "{entry.vlm_description}"
            </div>
          )}
        </div>
      )}

      {hasEvidence && (
        <div style={{ marginTop: 8, position: 'relative', overflow: 'hidden', border: '1px solid var(--border)', background: '#000', maxHeight: 150 }}>
          <img 
            src={`\${backendUrl}/evidence/\${entry.evidence}`} 
            alt="Evidence Capture" 
            style={{ width: '100%', height: 'auto', display: 'block', opacity: 0.85, objectFit: 'cover' }}
          />
          <div style={{ 
            position: 'absolute', bottom: 0, left: 0, right: 0, 
            background: 'linear-gradient(transparent, rgba(0,0,0,0.8))', 
            padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' 
          }}>
            <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.6)', fontFamily: 'var(--mono)' }}>EVIDENCE_CAPTURE.JPG</span>
            <a 
              href={`\${backendUrl}/evidence/\${entry.evidence}`} 
              target="_blank" 
              rel="noopener noreferrer" 
              style={{ fontSize: 9, color: 'var(--accent)', fontWeight: 700, textDecoration: 'none' }}
            >
              VIEW FULLSIZE
            </a>
          </div>
        </div>
      )}
    </div>
  );
};

export default function AIAnalytics({
  cameras = [], isBackendOffline, stats, trackingCameras,
  backendUrl = BACKEND
}) {
  const [activeMods, setActiveMods] = useState(new Set());
  const [selCams, setSelCams]       = useState(new Set());
  const [camQ, setCamQ]             = useState('');
  const [running, setRunning]       = useState(false);
  const [expandedCam, setExpandedCam] = useState(null);

  const [alertLogs, setAlertLogs] = useState([]);
  const [vlmLogs, setVlmLogs]     = useState([]);
  const [sysLogs, setSysLogs]     = useState([]);

  const filtCams = cameras.filter(c => {
    const q = camQ.trim().toLowerCase();
    return !q || c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q);
  });

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const [alertRes, vlmRes, sysRes] = await Promise.all([
          fetch(`\${backendUrl}/api/alert_logs`),
          fetch(`\${backendUrl}/api/vlm_logs`),
          fetch(`\${backendUrl}/api/logs`)
        ]);
        if (alertRes.ok) setAlertLogs(await alertRes.json());
        if (vlmRes.ok)   setVlmLogs(await vlmRes.json());
        if (sysRes.ok)   setSysLogs(await sysRes.json());
      } catch (_) {}
    };
    fetchLogs();
    const interval = setInterval(fetchLogs, 2500);
    return () => clearInterval(interval);
  }, [backendUrl]);

  const toggleCam = id => setSelCams(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelCams(new Set(filtCams.map(c => c.id)));
  const clearAll  = () => setSelCams(new Set());

  const handleModClick = id => {
    if (running) handleStop();
    setActiveMods(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const handleRun = async () => {
    if (!running) {
      if (activeMods.size === 0 || selCams.size === 0) return;
      setRunning(true);
      try {
        await fetch(`\${backendUrl}/api/ai_analytics/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ modules: Array.from(activeMods), cameras: Array.from(selCams) })
        });
      } catch(e) {}
    } else {
      handleStop();
    }
  };

  const handleStop = async () => {
    setRunning(false);
    try {
      await fetch(`\${backendUrl}/api/ai_analytics/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cameras: Array.from(selCams) })
      });
    } catch(e) {}
  };

  const clearLogs = async (channel) => {
    try { 
      await fetch(`\${backendUrl}/api/\${channel}/clear`, { method: 'POST' }); 
      if(channel === 'alert_logs') setAlertLogs([]);
      if(channel === 'vlm_logs') setVlmLogs([]);
      if(channel === 'logs') setSysLogs([]);
    } catch(_) {}
  };

  return (
    <div className="page-container">
      
      {/* ——— 3 COLUMN LAYOUT ——— */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr 340px', gap: '20px', flex: 1, minHeight: 0, height: '100%' }}>
        
        {/* LEFT COL: CONTROLS */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0 }}>
          
          <div className="card" style={{ flex: 1, minHeight: 0 }}>
            <div className="card-header">
              <span className="card-title">1. SELECT CAMERAS</span>
              <span className="tag tag-muted">{selCams.size} SEL</span>
            </div>
            <div style={{ display: 'flex', padding: 12, gap: 8, background: 'var(--bg-surface)', borderBottom: '1px solid var(--border-light)' }}>
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '6px 10px' }}>
                <Search size={14} color="var(--text-muted)"/>
                <input placeholder="Search..." value={camQ} onChange={e => setCamQ(e.target.value)} style={{ border: 'none', outline: 'none', background: 'transparent', width: '100%', fontSize: 11, fontFamily: 'var(--mono)' }}/>
              </div>
            </div>
            <div style={{ display: 'flex', padding: '8px 12px', gap: 8, borderBottom: '1px solid var(--border)' }}>
              <button className="btn btn-outline" style={{ flex: 1, padding: '4px 0', fontSize: 10 }} onClick={selectAll}>ALL</button>
              <button className="btn btn-outline" style={{ flex: 1, padding: '4px 0', fontSize: 10 }} onClick={clearAll}>CLEAR</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {filtCams.map(cam => {
                const sel = selCams.has(cam.id);
                return (
                  <div key={cam.id} onClick={() => toggleCam(cam.id)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', cursor: 'pointer', background: sel ? 'var(--bg-card)' : 'var(--bg-surface)', border: `1px solid \${sel ? 'var(--accent)' : 'var(--border-light)'}` }}>
                    {sel ? <CheckCircle2 size={16} color="var(--accent)"/> : <div style={{ width: 16, height: 16, border: '1px solid var(--border-strong)' }} />}
                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-main)', flex: 1 }}>{cam.name}</span>
                    <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-muted)' }}>#{cam.id}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card" style={{ flex: 1, minHeight: 0 }}>
            <div className="card-header">
              <span className="card-title">2. AI MODULES</span>
              <span className="tag tag-muted">{activeMods.size} ACTIVE</span>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {MODS.map(m => {
                const on = activeMods.has(m.id);
                return (
                  <div key={m.id} onClick={() => handleModClick(m.id)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px', cursor: 'pointer', background: on ? 'var(--bg-card)' : 'var(--bg-surface)', border: `1px solid \${on ? m.accent : 'var(--border-light)'}`, boxShadow: on ? `inset 3px 0 0 \${m.accent}` : 'none' }}>
                    <Activity size={18} color={on ? m.accent : 'var(--text-muted)'}/>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--text-main)' }}>{m.name}</div>
                      <div style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-muted)' }}>{m.engine}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <button className={`btn \${running ? 'btn-danger' : 'btn-primary'}`} style={{ padding: 16, fontSize: 14 }} onClick={handleRun} disabled={activeMods.size === 0 || (!running && selCams.size === 0)}>
            {running ? <><Square size={16} fill="currentColor"/> STOP ORCHESTRATION</> : <><Play size={16} fill="currentColor"/> START AI ANALYSIS</>}
          </button>
        </div>

        {/* CENTER COL: VIDEO GRID */}
        <div className="card" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <div className="card-header" style={{ flexShrink: 0 }}>
            <span className="card-title"><Video size={14} color="var(--info)" /> LIVE CAMERA GRID</span>
            <button className="btn btn-outline" style={{ padding: '4px 8px', fontSize: 10 }} onClick={() => setSelCams(new Set())}>✖ CLOSE ALL</button>
          </div>
          
          <div style={{ flex: 1, overflowY: 'auto', padding: 16, background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column' }}>
            {selCams.size > 0 ? (
              <div style={{ 
                  display: 'grid', 
                  gap: 16, 
                  gridTemplateColumns: expandedCam ? '1fr' :
                                     selCams.size === 1 ? '1fr' :
                                     selCams.size === 2 ? '1fr 1fr' :
                                     selCams.size <= 4 ? '1fr 1fr' :
                                     selCams.size <= 6 ? '1fr 1fr 1fr' :
                                     selCams.size <= 9 ? '1fr 1fr 1fr' :
                                     'repeat(auto-fit, minmax(240px, 1fr))',
                  gridTemplateRows: expandedCam ? '1fr' :
                                  selCams.size <= 2 ? '1fr' :
                                  selCams.size <= 6 ? '1fr 1fr' :
                                  selCams.size <= 9 ? '1fr 1fr 1fr' :
                                  'auto',
                  flex: 1,
                  width: '100%',
                  height: '100%'
                }}>
                {[...selCams].filter(id => !expandedCam || expandedCam === id).map(id => {
                  const cam = cameras.find(c => c.id === id);
                  if (!cam) return null;
                  return (
                    <CamGridCell key={id} cam={cam} isTracking={!!trackingCameras?.[id] || running}
                      onExpand={cid => setExpandedCam(prev => prev === cid ? null : cid)}
                      isExpanded={expandedCam === id}
                      onRemove={cid => { setSelCams(p => { const n = new Set(p); n.delete(cid); return n; }); if(expandedCam===cid) setExpandedCam(null); }}
                      backendUrl={backendUrl}/>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">
                <Crosshair size={48} color="var(--border-strong)" />
                <div className="empty-state-title">No Cameras Selected</div>
                <div className="empty-state-sub">Select cameras and press START to begin live orchestration.</div>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COL: LOGS */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0 }}>
          <div className="card" style={{ flex: 1, minHeight: 0 }}>
            <div className="card-header" style={{ borderBottom: '2px solid var(--danger)' }}>
              <span className="card-title" style={{ color: 'var(--danger)' }}><ShieldAlert size={14} /> ACTIONABLE ALERTS</span>
              <button className="btn btn-outline" style={{ padding: '2px 6px', fontSize: 9 }} onClick={() => clearLogs('alert_logs')}><Trash2 size={10}/></button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {alertLogs.length === 0 ? (
                <div className="empty-state" style={{ padding: 20 }}>No active alerts.</div>
              ) : (
                alertLogs.map(e => <AlertRow key={e.id} entry={e} backendUrl={backendUrl} />)
              )}
            </div>
          </div>

          <div className="card" style={{ flex: 1, minHeight: 0 }}>
            <div className="card-header" style={{ borderBottom: '2px solid var(--info)' }}>
              <span className="card-title" style={{ color: 'var(--info)' }}><ShieldCheck size={14} /> VLM ANALYSIS</span>
              <button className="btn btn-outline" style={{ padding: '2px 6px', fontSize: 9 }} onClick={() => clearLogs('vlm_logs')}><Trash2 size={10}/></button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {vlmLogs.length === 0 ? (
                <div className="empty-state" style={{ padding: 20 }}>Waiting for VLM analysis...</div>
              ) : (
                vlmLogs.map(e => <LogRow key={e.id} entry={e} />)
              )}
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
