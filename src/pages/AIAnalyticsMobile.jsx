// v4-clean
import React, { useState, useEffect } from "react";
import { Play, Square, X, ChevronRight, ChevronLeft, Video, AlertCircle, CheckCircle2 } from "lucide-react";

const BACKEND = "http://127.0.0.1:5001";

const MODULES = [
  { id: "people",     name: "People Count",    desc: "Density & tracking",     accent: "#0EA5E9" },
  { id: "posture",    name: "Fall Detection",   desc: "Collapse detection",     accent: "#8B5CF6" },
  { id: "stglad",    name: "ST-GLAD",          desc: "Crowd chaos detection",  accent: "#EF4444" },
  { id: "perimeter",  name: "Perimeter Guard",  desc: "Wall climbing alerts",   accent: "#F59E0B" },
  { id: "intrusion",  name: "Zone Intrusion",   desc: "Restricted area access", accent: "#E11D48" },
  { id: "sliphazard", name: "Slip Hazard",      desc: "Floor & obstacle scan",  accent: "#10B981" },
];

const FeedCell = ({ cam, isTracking, onExpand, isExpanded, onRemove, backendUrl }) => (
  <div style={{
    position: "relative", background: "#000",
    border: isTracking ? "2px solid #3B82F6" : "2px solid #1E1E1E",
    overflow: "hidden", height: "100%", width: "100%"
  }}>
    <div style={{
      position: "absolute", top: 0, left: 0, right: 0, zIndex: 2,
      padding: "6px 8px",
      background: "linear-gradient(180deg,rgba(0,0,0,0.75)0%,transparent 100%)",
      display: "flex", justifyContent: "space-between", alignItems: "center",
    }}>
      <span style={{ color: "#fff", fontSize: 10, fontWeight: 600, fontFamily: "monospace" }}>
        {isTracking && <span style={{ color: "#EF4444", marginRight: 5, animation: "blink 1.2s infinite" }}>●</span>}
        {cam.name}
      </span>
      <div style={{ display: "flex", gap: 3 }}>
        <button onClick={e => { e.stopPropagation(); onExpand(cam.id); }}
          style={{ background: "rgba(255,255,255,0.12)", border: "none", color: "#ccc", width: 20, height: 20, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {isExpanded ? "-" : "+"}
        </button>
        <button onClick={e => { e.stopPropagation(); onRemove(cam.id); }}
          style={{ background: "rgba(220,38,38,0.65)", border: "none", color: "#fff", width: 20, height: 20, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <X size={9} />
        </button>
      </div>
    </div>
    <img
      src={`${backendUrl}/video_feed/${cam.id}?detect=${isTracking}`}
      alt={cam.name}
      style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
      onError={e => { e.target.style.display = "none"; if (e.target.nextElementSibling) e.target.nextElementSibling.style.display = "flex"; }}
    />
    <div style={{
      display: "none", position: "absolute", inset: 0,
      alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8, color: "#333",
    }}>
      <Video size={22} />
      <span style={{ fontSize: 9, fontFamily: "monospace", letterSpacing: 1 }}>NO SIGNAL</span>
    </div>
    {isTracking && (
      <div style={{ position: "absolute", bottom: 5, right: 6, background: "#DC2626", color: "#fff", fontSize: 8, fontWeight: 800, fontFamily: "monospace", letterSpacing: 1, padding: "2px 5px" }}>LIVE</div>
    )}
  </div>
);

export default function AIAnalytics({ cameras = [], trackingCameras, backendUrl = BACKEND }) {
  const [activeMods, setActiveMods] = useState(new Set());
  const [selCams, setSelCams]       = useState(new Set());
  const [camDrawer, setCamDrawer]   = useState(false);
  const [running, setRunning]       = useState(false);
  const [expandedCam, setExpandedCam] = useState(null);
  const [alertCount, setAlertCount] = useState(0);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${backendUrl}/api/alert_logs`);
        if (r.ok) { const d = await r.json(); setAlertCount(d.length); }
      } catch (_) {}
    };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [backendUrl]);

  const toggleCam = id => setSelCams(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleMod = id => setActiveMods(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const handleRun = async () => {
    if (running) {
      setRunning(false);
      try { await fetch(`${backendUrl}/api/ai_analytics/stop`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cameras: [...selCams] }) }); } catch (_) {}
      return;
    }
    if (!selCams.size || !activeMods.size) return;
    setRunning(true);
    try { await fetch(`${backendUrl}/api/ai_analytics/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modules: [...activeMods], cameras: [...selCams] }) }); } catch (_) {}
  };

  const canStart = selCams.size > 0 && activeMods.size > 0;
  const cols = expandedCam ? 1 : selCams.size <= 1 ? 1 : selCams.size <= 4 ? 2 : 3;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", background: "#F1F5F9", position: "relative" }}>
      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.25} }
        @keyframes slideIn { from{transform:translateX(-100%)} to{transform:translateX(0)} }
        @keyframes slideOut { from{transform:translateX(0)} to{transform:translateX(-100%)} }
      `}</style>

      {/* ── Camera Drawer Overlay ─────────────────────────── */}
      {camDrawer && (
        <>
          {/* Backdrop */}
          <div
            onClick={() => setCamDrawer(false)}
            style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.25)", zIndex: 50 }}
          />
          {/* Drawer panel */}
          <div style={{
            position: "absolute", top: 0, left: 0, bottom: 0,
            width: 260, background: "#fff",
            borderRight: "1px solid #E2E8F0",
            zIndex: 51, display: "flex", flexDirection: "column",
            animation: "slideIn 0.2s ease",
            boxShadow: "4px 0 20px rgba(0,0,0,0.12)",
          }}>
            {/* Drawer header */}
            <div style={{ padding: "14px 16px", borderBottom: "1px solid #E2E8F0", display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>Camera Streams</div>
                <div style={{ fontSize: 10, color: "#94A3B8", marginTop: 1 }}>{selCams.size} of {cameras.length} selected</div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <button onClick={() => setSelCams(new Set(cameras.map(c => c.id)))}
                  style={{ padding: "3px 8px", fontSize: 10, background: "#F8FAFC", border: "1px solid #E2E8F0", cursor: "pointer", color: "#475569" }}>All</button>
                <button onClick={() => setSelCams(new Set())}
                  style={{ padding: "3px 8px", fontSize: 10, background: "#F8FAFC", border: "1px solid #E2E8F0", cursor: "pointer", color: "#94A3B8" }}>Clr</button>
                <button onClick={() => setCamDrawer(false)}
                  style={{ width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center", background: "#F1F5F9", border: "1px solid #E2E8F0", cursor: "pointer", color: "#64748B" }}>
                  <X size={12} />
                </button>
              </div>
            </div>
            {/* Camera list */}
            <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              {cameras.length === 0 ? (
                <div style={{ padding: 20, textAlign: "center", color: "#CBD5E1", fontSize: 12 }}>No cameras available</div>
              ) : cameras.map(cam => {
                const sel = selCams.has(cam.id);
                return (
                  <div key={cam.id} onClick={() => toggleCam(cam.id)} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
                    borderBottom: "1px solid #F8FAFC",
                    borderLeft: sel ? "3px solid #2563EB" : "3px solid transparent",
                    background: sel ? "#EFF6FF" : "#fff", cursor: "pointer",
                  }}>
                    <div style={{
                      width: 16, height: 16, flexShrink: 0,
                      border: `2px solid ${sel ? "#2563EB" : "#CBD5E1"}`,
                      background: sel ? "#2563EB" : "transparent",
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                      {sel && <svg width="8" height="6" viewBox="0 0 8 6"><path d="M1 3L3 5L7 1" stroke="white" strokeWidth="1.5" strokeLinecap="square" fill="none"/></svg>}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: sel ? 600 : 400, color: sel ? "#1E40AF" : "#334155", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{cam.name}</div>
                      <div style={{ fontSize: 9, color: "#94A3B8", fontFamily: "monospace" }}>#{cam.id}</div>
                    </div>
                    {sel && <CheckCircle2 size={13} color="#2563EB" />}
                  </div>
                );
              })}
            </div>
            {/* Drawer footer: close */}
            <div style={{ padding: "12px 16px", borderTop: "1px solid #E2E8F0", flexShrink: 0 }}>
              <button onClick={() => setCamDrawer(false)} style={{
                width: "100%", padding: "9px 0", fontSize: 12, fontWeight: 600,
                background: "#2563EB", color: "#fff", border: "none", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              }}>
                <ChevronLeft size={13} /> Done — Close Panel
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── MAIN LAYOUT (column) ──────────────────────────── */}

      {/* Top bar */}
      <div style={{
        height: 44, background: "#fff", borderBottom: "1px solid #E2E8F0",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 16px", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Camera drawer toggle */}
          <button
            onClick={() => setCamDrawer(true)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 12px",
              background: selCams.size > 0 ? "#EFF6FF" : "#F8FAFC",
              border: selCams.size > 0 ? "1px solid #BFDBFE" : "1px solid #E2E8F0",
              color: selCams.size > 0 ? "#1E40AF" : "#64748B",
              cursor: "pointer", fontSize: 11, fontWeight: 600,
            }}
          >
            <ChevronRight size={13} />
            Cameras
            {selCams.size > 0 && (
              <span style={{ background: "#2563EB", color: "#fff", fontSize: 9, fontWeight: 800, padding: "1px 6px", minWidth: 16, textAlign: "center" }}>
                {selCams.size}
              </span>
            )}
          </button>

          {/* Status pills */}
          {running && (
            <div style={{ display: "flex", alignItems: "center", gap: 5, background: "#FEF2F2", border: "1px solid #FECACA", padding: "3px 10px" }}>
              <span style={{ width: 6, height: 6,  background: "#EF4444", display: "inline-block", animation: "blink 1.2s infinite" }} />
              <span style={{ fontSize: 10, fontWeight: 700, color: "#EF4444", fontFamily: "monospace", letterSpacing: 1 }}>LIVE</span>
            </div>
          )}
          {alertCount > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, color: "#B45309", fontSize: 11, fontWeight: 600 }}>
              <AlertCircle size={12} />
              {alertCount} alert{alertCount !== 1 ? "s" : ""}
            </div>
          )}
        </div>

        <span style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>AI Orchestration</span>
      </div>

      {/* ── VIDEO VIEWER (takes all remaining space) ──────── */}
      <div style={{ flex: 1, minHeight: 0, background: "#0D0D0D", position: "relative", overflow: "hidden" }}>
        {selCams.size > 0 ? (
          <div style={{ height: "100%", width: "100%", padding: 10 }}>
            <div style={{ display: "grid", gap: 8, height: "100%", gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${Math.ceil((expandedCam ? 1 : selCams.size) / cols)}, 1fr)` }}>
              {[...selCams]
                .filter(id => !expandedCam || expandedCam === id)
                .map(id => {
                  const cam = cameras.find(c => c.id === id);
                  if (!cam) return null;
                  return (
                    <FeedCell key={id} cam={cam}
                      isTracking={!!trackingCameras?.[id] || running}
                      onExpand={cid => setExpandedCam(p => p === cid ? null : cid)}
                      isExpanded={expandedCam === id}
                      onRemove={cid => { setSelCams(p => { const n = new Set(p); n.delete(cid); return n; }); if (expandedCam === cid) setExpandedCam(null); }}
                      backendUrl={backendUrl}
                    />
                  );
                })}
            </div>
          </div>
        ) : (
          <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "#2D2D2D" }}>
            <Video size={40} strokeWidth={1} />
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 13, color: "#3F3F3F", fontWeight: 500, marginBottom: 4 }}>No feeds selected</div>
              <div style={{ fontSize: 11, color: "#2A2A2A" }}>
                Click <strong style={{ color: "#9CA3AF" }}>Cameras</strong> in the top left to choose streams
              </div>
            </div>
            <button onClick={() => setCamDrawer(true)} style={{
              marginTop: 4, padding: "8px 20px", background: "transparent",
              border: "1px solid #333", color: "#9CA3AF", fontSize: 11, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <ChevronRight size={12} /> Open Camera Panel
            </button>
          </div>
        )}
      </div>

      {/* ── AI MODULES (small scrollable bar) ─────────────── */}
      <div style={{
        background: "#fff", borderTop: "1px solid #E2E8F0", flexShrink: 0,
      }}>
        <div style={{ padding: "8px 16px 4px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: "#64748B", letterSpacing: 0.8, textTransform: "uppercase" }}>
            AI Engines
          </span>
          <span style={{ fontSize: 10, color: "#94A3B8" }}>
            {activeMods.size} / {MODULES.length} active
          </span>
        </div>
        {/* Horizontally scrollable modules */}
        <div style={{ overflowX: "auto", padding: "6px 16px 10px", display: "flex", gap: 8 }}>
          {MODULES.map(m => {
            const on = activeMods.has(m.id);
            return (
              <div key={m.id} onClick={() => toggleMod(m.id)} style={{
                flexShrink: 0, width: 140, padding: "9px 12px",
                border: on ? `1.5px solid ${m.accent}` : "1.5px solid #E2E8F0",
                borderTop: on ? `3px solid ${m.accent}` : "3px solid transparent",
                background: on ? `${m.accent}0A` : "#FAFAFA",
                cursor: "pointer", transition: "all 0.12s",
              }}>
                <div style={{ fontSize: 11, fontWeight: on ? 700 : 500, color: on ? "#0F172A" : "#64748B", marginBottom: 2 }}>{m.name}</div>
                <div style={{ fontSize: 9, color: "#94A3B8" }}>{m.desc}</div>
                <div style={{ marginTop: 6, width: on ? "100%" : 0, height: 2, background: m.accent, transition: "width 0.2s" }} />
              </div>
            );
          })}
        </div>
      </div>

      {/* ── START / STOP BUTTON ───────────────────────────── */}
      <div style={{ background: "#fff", borderTop: "1px solid #E2E8F0", padding: "10px 16px", flexShrink: 0 }}>
        <button
          onClick={handleRun}
          disabled={!running && !canStart}
          style={{
            width: "100%", padding: "11px 0",
            fontSize: 13, fontWeight: 700,
            background: running ? "#DC2626" : canStart ? "#2563EB" : "#E2E8F0",
            color: running || canStart ? "#fff" : "#94A3B8",
            border: "none", cursor: !running && !canStart ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            transition: "background 0.15s",
            opacity: !running && !canStart ? 0.6 : 1,
          }}
        >
          {running
            ? <><Square size={13} fill="currentColor" /> Stop Analysis</>
            : <><Play  size={13} fill="currentColor" /> Start Analysis</>
          }
        </button>
        {!canStart && !running && (
          <div style={{ textAlign: "center", fontSize: 10, color: "#CBD5E1", marginTop: 5 }}>
            {selCams.size === 0 && activeMods.size === 0 && "Select cameras and at least one engine"}
            {selCams.size === 0 && activeMods.size > 0 && "Open the camera panel and select streams"}
            {selCams.size > 0  && activeMods.size === 0 && "Select at least one AI engine above"}
          </div>
        )}
      </div>

    </div>
  );
}



