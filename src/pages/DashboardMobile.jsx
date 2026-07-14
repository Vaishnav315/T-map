import React, { useState } from 'react';
import { MapContainer, TileLayer, ImageOverlay, CircleMarker, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Layers, ZoomIn, ZoomOut, LocateFixed, RefreshCw, ChevronRight, X, Video, ShieldCheck, MapPin } from 'lucide-react';

import BlueprintInitializer from '../components/Map/BlueprintInitializer';
import ZoomAwareMarkers    from '../components/Map/ZoomAwareMarkers';
import MapController       from '../components/Map/MapController';
import MatrixClickTracker  from '../components/Map/MatrixClickTracker';
import BlindSpotEditor     from '../components/Map/BlindSpotEditor';
import { MAP_CENTER, MAP_ZOOM, BLUEPRINT_CONFIG, MAP_LAYERS, BLIND_SPOTS } from '../constants/mapConfig';

function MapZoomControl({ onFit }) {
  const map = useMap();
  return (
    <div className="map-ctrl-grp" style={{ top: 10, right: 10, display: "flex", flexDirection: "column", gap: 5, position: "absolute", zIndex: 400 }}>
      <button style={{ width: 32, height: 32, background: "#fff", border: "1px solid #ccc", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => map.zoomIn()}><ZoomIn size={16} /></button>
      <button style={{ width: 32, height: 32, background: "#fff", border: "1px solid #ccc", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => map.zoomOut()}><ZoomOut size={16} /></button>
      <button style={{ width: 32, height: 32, background: "#fff", border: "1px solid #ccc", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onFit}><LocateFixed size={16} /></button>
    </div>
  );
}

export default function Dashboard_NEW({
  stats, filteredCameras, activeCamera, handleSelectCamera, isBlueprint,
  activeTab, setActiveTab, zones, mapLayer, showLayerMenu, setShowLayerMenu, handleLayerSwitch,
  trackingCameras, handleToggleTracking, unreadAlerts, mapCameras, selectedWorkerId, setSelectedWorkerId
}) {
  const [camDrawer, setCamDrawer] = useState(false);
  const [showBlindSpots, setShowBlindSpots] = useState(false);
  const [blindSpots, setBlindSpots] = useState(BLIND_SPOTS);

  const safeCount = stats?.person_count || 0;
  const safeAlerts = unreadAlerts || stats?.active_alerts || 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#F1F5F9", position: "relative", overflow: "hidden" }}>
      <style>{`
        @keyframes slideInLeft {
          from { transform: translateX(-100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
      
      {/* ── DRAWER ────────────────────────────────────────────────────────── */}
      {camDrawer && (
        <>
          <div onClick={() => setCamDrawer(false)} style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 1000 }} />
          <div style={{
            position: "absolute", top: 0, left: 0, bottom: 0, width: 280, background: "#fff", zIndex: 1001,
            display: "flex", flexDirection: "column", animation: "slideInLeft 0.2s ease", boxShadow: "4px 0 20px rgba(0,0,0,0.15)"
          }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid #E2E8F0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>Settings & Cameras</div>
              <button onClick={() => setCamDrawer(false)} style={{ background: "transparent", border: "none", cursor: "pointer", color: "#64748B" }}><X size={16} /></button>
            </div>
            
            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
              {/* Stats */}
              <div style={{ padding: 16, display: "flex", gap: 10, borderBottom: "1px solid #F1F5F9" }}>
                <div style={{ flex: 1, background: "#F0F9FF", border: "1px solid #BAE6FD", padding: 10, textAlign: "center" }}>
                  <div style={{ fontSize: 18, fontWeight: 800, color: "#0369A1" }}>{safeCount}</div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "#0EA5E9" }}>PERSONNEL</div>
                </div>
                <div style={{ flex: 1, background: safeAlerts > 0 ? "#FEF2F2" : "#F0FDF4", border: `1px solid ${safeAlerts > 0 ? "#FECACA" : "#BBF7D0"}`, padding: 10, textAlign: "center" }}>
                  <div style={{ fontSize: 18, fontWeight: 800, color: safeAlerts > 0 ? "#DC2626" : "#16A34A" }}>{safeAlerts}</div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: safeAlerts > 0 ? "#EF4444" : "#22C55E" }}>ALERTS</div>
                </div>
              </div>

              {/* Cameras */}
              <div style={{ padding: "12px 16px 8px", fontSize: 11, fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>Camera Streams</div>
              <div style={{ display: "flex", flexDirection: "column" }}>
                {filteredCameras.map(cam => {
                  const isSel = activeCamera?.id === cam.id;
                  const isTracking = trackingCameras[cam.id];
                  const pCount = Array.isArray(stats?.cameras) ? stats.cameras.find(c => String(c.id) === String(cam.id))?.person_count : 0;
                  
                  return (
                    <div key={cam.id} onClick={() => { handleSelectCamera(cam.id); setCamDrawer(false); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
                        borderBottom: "1px solid #F8FAFC", cursor: "pointer",
                        borderLeft: isSel ? "3px solid #2563EB" : "3px solid transparent",
                        background: isSel ? "#EFF6FF" : "#fff"
                      }}>
                      <Video size={16} color={isSel ? "#2563EB" : "#94A3B8"} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: isSel ? 600 : 500, color: isSel ? "#1E40AF" : "#334155" }}>{cam.name}</div>
                        <div style={{ fontSize: 10, color: "#94A3B8", fontFamily: "monospace" }}>#{cam.id}</div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        {pCount > 0 && <span style={{ background: "#0EA5E9", color: "#fff", fontSize: 10, padding: "2px 6px", fontWeight: 700 }}>{pCount}</span>}
                        <button onClick={(e) => { e.stopPropagation(); handleToggleTracking(cam.id); }}
                          style={{
                            padding: "4px 8px", fontSize: 9, fontWeight: 700, border: "none", cursor: "pointer",
                            background: isTracking ? "#2563EB" : "#F1F5F9",
                            color: isTracking ? "#fff" : "#64748B"
                          }}>
                          {isTracking ? "● LIVE" : "TRACK"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── TOP HEADER ──────────────────────────────────────────────────────── */}
      <div style={{ height: 48, background: "#fff", borderBottom: "1px solid #E2E8F0", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px", flexShrink: 0, zIndex: 1000 }}>
        <button onClick={() => setCamDrawer(true)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", background: "#F8FAFC", border: "1px solid #E2E8F0", color: "#475569", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
          <ChevronRight size={14} /> Cameras
        </button>
        <span style={{ fontSize: 14, fontWeight: 700, color: "#0F172A", letterSpacing: 0.5 }}>LIVE MAP</span>
        <div style={{ width: 85 }} /> {/* Spacer to center title */}
      </div>

      {/* ── MAP AREA ────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, position: "relative", zIndex: 1, background: "#E2E8F0" }}>
        
        {/* Layer Controls Dropdown */}
        <div style={{ position: "absolute", top: 10, left: 10, zIndex: 1000, display: "flex", flexDirection: "column", gap: 8 }}>
          <button onClick={() => setShowLayerMenu(!showLayerMenu)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", background: "#fff", border: "1px solid #ccc", color: "#333", fontSize: 11, fontWeight: 700, cursor: "pointer", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
            <Layers size={14} /> LAYERS
          </button>
          {showLayerMenu && (
            <div style={{ background: "#fff", border: "1px solid #ccc", padding: "4px", boxShadow: "0 4px 12px rgba(0,0,0,0.15)", width: 160, maxHeight: 300, overflowY: "auto" }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "#94A3B8", padding: "4px 8px", textTransform: "uppercase" }}>Map Type</div>
              {Object.entries(MAP_LAYERS).map(([key, layer]) => (
                <div key={key} onClick={() => { handleLayerSwitch(key); setShowLayerMenu(false); }} style={{ padding: "8px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", borderBottom: "1px solid #eee", background: mapLayer === key ? "#EFF6FF" : "transparent" }}>
                  {layer.name}
                </div>
              ))}
              <div style={{ fontSize: 9, fontWeight: 700, color: "#94A3B8", padding: "8px 8px 4px", textTransform: "uppercase" }}>Overlays</div>
              <div style={{ padding: "8px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }} onClick={() => setShowBlindSpots(!showBlindSpots)}>
                <input type="checkbox" checked={showBlindSpots} onChange={() => {}} style={{ margin: 0 }} />
                <span>Blind Spots</span>
              </div>
            </div>
          )}
        </div>

        {/* Zone Tabs (if any) */}
        {zones && zones.length > 1 && (
          <div style={{ position: "absolute", bottom: 16, left: 16, right: 16, zIndex: 1000, display: "flex", gap: 6, overflowX: "auto", whiteSpace: "nowrap", paddingBottom: 4 }}>
            {zones.map(z => (
              <button key={z} onClick={() => setActiveTab(z)} style={{ padding: "6px 14px", fontSize: 11, fontWeight: 700, cursor: "pointer", border: "none", boxShadow: "0 2px 6px rgba(0,0,0,0.15)", background: activeTab === z ? "#2563EB" : "#fff", color: activeTab === z ? "#fff" : "#333" }}>
                {z}
              </button>
            ))}
          </div>
        )}

        <MapContainer
          key={mapLayer}
          crs={isBlueprint ? L.CRS.Simple : L.CRS.EPSG3857}
          center={isBlueprint ? [BLUEPRINT_CONFIG.height / 2, BLUEPRINT_CONFIG.width / 2] : MAP_CENTER}
          zoom={isBlueprint ? 0 : MAP_ZOOM}
          maxZoom={isBlueprint ? 4 : 24}
          minZoom={isBlueprint ? -2 : 16}
          zoomAnimation={!isBlueprint}
          zoomControl={false}
          style={{ height: '100%', width: '100%' }}
        >
          <MapController center={isBlueprint ? [BLUEPRINT_CONFIG.height / 2, BLUEPRINT_CONFIG.width / 2] : MAP_CENTER} zoom={isBlueprint ? 0 : MAP_ZOOM} />
          <MapZoomControl onFit={() => {}} />

          {isBlueprint ? (
            <>
              <BlueprintInitializer />
              <ImageOverlay url={BLUEPRINT_CONFIG.url} bounds={[[0,0],[BLUEPRINT_CONFIG.height, BLUEPRINT_CONFIG.width]]} opacity={0.94} />
            </>
          ) : (
            <TileLayer url={MAP_LAYERS[mapLayer].url} maxNativeZoom={21} maxZoom={24} />
          )}

          <ZoomAwareMarkers 
            cameras={mapCameras} 
            activeCamera={activeCamera} 
            stats={stats} 
            onSelect={handleSelectCamera}
            isBlueprint={isBlueprint} 
            accent="#2563EB"
            trackingCameras={trackingCameras}
          />

          <MatrixClickTracker activeTab={activeTab} />

          {showBlindSpots && (
            <BlindSpotEditor 
              isBlueprint={isBlueprint}
              isDrawingMode={false}
              blindSpots={blindSpots}
              setBlindSpots={setBlindSpots}
            />
          )}

          {/* Worker Markers */}
          {(stats?.cameras || []).flatMap(cam =>
            (cam.tracked_positions || []).map((worker, idx) => ({ ...worker, cam_id: cam.id, idx }))
          ).map((worker) => {
            const currentPos = isBlueprint ? worker.blueprint_pos : worker.pos;
            if (!currentPos || currentPos.length < 2) return null;
            const stableId = worker.tid !== -1 ? worker.tid : null;
            const uniqueId = `${worker.cam_id}-${stableId ?? worker.idx}`;
            const isIso = stableId !== null && selectedWorkerId === uniqueId;
            const fillColor = isIso ? '#2563EB' : '#0EA5E9';
            return (
              <React.Fragment key={uniqueId}>
                <CircleMarker
                  center={currentPos} radius={isIso ? 8 : 5}
                  pathOptions={{ fillColor, color: '#fff', weight: 2, fillOpacity: 1 }}
                  eventHandlers={{ click: (e) => { L.DomEvent.stopPropagation(e); if (stableId) setSelectedWorkerId(isIso ? null : uniqueId); }}}
                >
                  <Tooltip permanent={isIso} direction="top" offset={[0,-5]} opacity={1}>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 'bold' }}>
                      {worker.tid !== -1 ? `Person ${worker.tid}` : 'Detecting'}
                    </span>
                  </Tooltip>
                </CircleMarker>
              </React.Fragment>
            );
          })}
        </MapContainer>
      </div>

    </div>
  );
}


