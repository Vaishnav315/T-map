import React, { useState, useEffect } from 'react';
import {
  MapContainer, TileLayer, ImageOverlay,
  CircleMarker, Tooltip, useMap
} from 'react-leaflet';
import L from 'leaflet';
import {
  Layers, Users, Activity, Video,
  ZoomIn, ZoomOut, LocateFixed, RefreshCw,
  Crosshair, MapPin, Search, ChevronDown, Clock, ShieldCheck,
  Maximize, Minimize, Wrench
} from 'lucide-react';

import BlueprintInitializer from '../components/Map/BlueprintInitializer';
import ZoomAwareMarkers from '../components/Map/ZoomAwareMarkers';
import MapController from '../components/Map/MapController';
import MatrixClickTracker from '../components/Map/MatrixClickTracker';
import BlindSpotEditor from '../components/Map/BlindSpotEditor';
import { MAP_CENTER, MAP_ZOOM, BLUEPRINT_CONFIG, MAP_LAYERS, BLIND_SPOTS } from '../constants/mapConfig';

function MapZoomControl({ onFit, isFullscreen, onToggleFullscreen }) {
  const map = useMap();
  return (
    <div className="map-ctrl-grp">
      <button className="map-btn" onClick={() => map.zoomIn()} title="Zoom In"><ZoomIn size={16} /></button>
      <button className="map-btn" onClick={() => map.zoomOut()} title="Zoom Out"><ZoomOut size={16} /></button>
      <button className="map-btn" onClick={onFit} title="Fit to view"><LocateFixed size={16} /></button>
      <button className="map-btn" onClick={onToggleFullscreen} title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}>
        {isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
      </button>
    </div>
  );
}

export default function Dashboard({
  accent, blueprintAccent, satelliteAccent, isBackendOffline, stats,
  filteredCameras, activeCamera, handleSelectCamera, isBlueprint,
  capturedCoord, setCapturedCoord, activeTab, setActiveTab, zones, alertLogs,
  mapLayer, showLayerMenu, setShowLayerMenu, handleLayerSwitch,
  trackingCameras, handleToggleTracking, selectedCoords,
  securityGateCounting, handleToggleSecurityGateCounting,
  mapCameras, trailDuration, handleTrailWindowUpdate, isSyncingSettings,
  selectedWorkerId, setSelectedWorkerId, unreadAlerts,
}) {
  const safeCount = isBackendOffline ? 0 : (Number(stats?.person_count) || 0);
  const safeAlerts = isBackendOffline ? 0 : (Number(unreadAlerts) || Number(stats?.active_alerts) || 0);
  const [searchQuery, setSearchQuery] = useState('');
  const [isMapFullscreen, setIsMapFullscreen] = useState(false);
  const [showBlindSpots, setShowBlindSpots] = useState(false);
  const [showDevTools, setShowDevTools] = useState(false);
  const [isDrawingMode, setIsDrawingMode] = useState(false);
  const [blindSpots, setBlindSpots] = useState(BLIND_SPOTS);

  const anyTracking = Object.values(trackingCameras).some(Boolean);

  const searchedCameras = filteredCameras.filter(cam => {
    const q = searchQuery.trim().toLowerCase();
    return !q || cam.id.toLowerCase().includes(q) || cam.name.toLowerCase().includes(q);
  });

  return (
    <div className="dash-layout" style={isMapFullscreen ? { padding: 0, gap: 0 } : {}}>

      {/* â•â•â•â•â•â• MAP CENTER â•â•â•â•â•â• */}
      <div className="dash-map-container" style={isMapFullscreen ? { border: 'none' } : {}}>
        <div className="dash-map-header">
          <div className="dash-map-title">LIVE MONITORING</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-outline" onClick={() => window.location.reload()}>
              <RefreshCw size={12} /> REFRESH
            </button>
            <button className={`btn ${showLayerMenu ? 'btn-primary' : 'btn-outline'}`} onClick={() => setShowLayerMenu(!showLayerMenu)}>
              <Layers size={12} /> LAYERS
            </button>
          </div>
        </div>

        <div className="map-wrapper">
          {isBlueprint && <div className="blueprint-scanlines" />}

          <MapContainer
            key={mapLayer}
            crs={isBlueprint ? L.CRS.Simple : L.CRS.EPSG3857}
            center={isBlueprint ? [BLUEPRINT_CONFIG.height / 2, BLUEPRINT_CONFIG.width / 2] : MAP_CENTER}
            zoom={isBlueprint ? 0 : MAP_ZOOM}
            maxZoom={isBlueprint ? 4 : 21}
            minZoom={isBlueprint ? -2 : 10}
            zoomAnimation={!isBlueprint}
            className="map-viewport"
            zoomControl={false}
          >
            {isBlueprint ? (
              <>
                <BlueprintInitializer />
                <ImageOverlay url={BLUEPRINT_CONFIG.url} bounds={[[0, 0], [BLUEPRINT_CONFIG.height, BLUEPRINT_CONFIG.width]]} opacity={0.94} />
                <MapZoomControl onFit={() => { }} isFullscreen={isMapFullscreen} onToggleFullscreen={() => setIsMapFullscreen(!isMapFullscreen)} />
              </>
            ) : (
              <>
                <TileLayer attribution={MAP_LAYERS[mapLayer].attribution} url={MAP_LAYERS[mapLayer].url} maxNativeZoom={MAP_LAYERS[mapLayer].maxNativeZoom} maxZoom={21} />
                <MapZoomControl onFit={() => { }} isFullscreen={isMapFullscreen} onToggleFullscreen={() => setIsMapFullscreen(!isMapFullscreen)} />
              </>
            )}

            <ZoomAwareMarkers cameras={mapCameras} activeCamera={activeCamera} onSelect={handleSelectCamera} isBlueprint={isBlueprint} />

            {/* Worker Markers */}
            {(stats?.cameras || []).flatMap(cam =>
              (cam.tracked_positions || []).map((worker, idx) => ({ ...worker, cam_id: cam.id, idx }))
            ).map((worker) => {
              const currentPos = isBlueprint ? worker.blueprint_pos : worker.pos;
              if (!currentPos || currentPos.length < 2) return null;
              const stableId = worker.tid !== -1 ? worker.tid : null;
              const uniqueId = `${worker.cam_id}-${stableId ?? worker.idx}`;
              const isIso = stableId !== null && selectedWorkerId === uniqueId;
              const fillColor = isIso ? 'var(--accent)' : 'var(--cyan)';
              return (
                <React.Fragment key={uniqueId}>
                  <CircleMarker
                    center={currentPos} radius={isIso ? 8 : 5}
                    pathOptions={{ fillColor, color: '#fff', weight: 2, fillOpacity: 1 }}
                    eventHandlers={{ click: (e) => { L.DomEvent.stopPropagation(e); if (stableId) setSelectedWorkerId(isIso ? null : uniqueId); } }}
                  >
                    <Tooltip permanent={isIso} direction="top" offset={[0, -5]} opacity={1}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 'bold' }}>
                        {worker.tid !== -1 ? `Person ${worker.tid}` : 'Detecting'}
                      </span>
                    </Tooltip>
                  </CircleMarker>
                </React.Fragment>
              );
            })}

            {!isBlueprint && <MapController selectedCoords={selectedCoords} />}
            {showDevTools && <MatrixClickTracker isBlueprint={isBlueprint} onCoord={setCapturedCoord} />}
            {showBlindSpots && (
              <BlindSpotEditor
                isBlueprint={isBlueprint}
                isDrawingMode={showDevTools && isDrawingMode}
                blindSpots={showDevTools ? blindSpots : BLIND_SPOTS}
                setBlindSpots={setBlindSpots}
              />
            )}
          </MapContainer>

          {/* FLOATING CONTROLS INSIDE MAP */}
          {showLayerMenu && (
            <div className="map-panel" style={{ width: 240 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: 'var(--text-muted)' }}>MAP VIEW</div>
              {Object.entries(MAP_LAYERS).map(([key, layer]) => (
                <div key={key} onClick={() => handleLayerSwitch(key)} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px', cursor: 'pointer', background: mapLayer === key ? 'var(--bg-surface)' : 'transparent', border: `1px solid ${mapLayer === key ? 'var(--accent)' : 'transparent'}` }}>
                  <div style={{ width: 8, height: 8, background: mapLayer === key ? 'var(--accent)' : 'var(--border)' }} />
                  <span style={{ fontSize: 11, fontWeight: 600 }}>{layer.name}</span>
                </div>
              ))}

              <div style={{ fontSize: 10, fontWeight: 800, color: 'var(--text-muted)', marginTop: 8 }}>GATE COUNTING</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 8px' }}>
                <input type="checkbox" checked={!!securityGateCounting['3']} onChange={() => handleToggleSecurityGateCounting('3')} />
                <span style={{ fontSize: 11 }}>Cam 3 â€” Gate Crossing (IN & OUT)</span>
              </div>

              <div style={{ fontSize: 10, fontWeight: 800, color: 'var(--text-muted)', marginTop: 8 }}>OVERLAYS</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 8px' }}>
                <input type="checkbox" checked={showBlindSpots} onChange={() => setShowBlindSpots(!showBlindSpots)} />
                <span style={{ fontSize: 11 }}>Blind Spots</span>
              </div>

              <div style={{ fontSize: 10, fontWeight: 800, color: 'var(--text-muted)', marginTop: 8 }}>DEVELOPER</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 8px' }}>
                <input type="checkbox" checked={showDevTools} onChange={() => setShowDevTools(!showDevTools)} />
                <span style={{ fontSize: 11 }}><Wrench size={12} style={{ marginRight: 4 }} /> Tools</span>
              </div>
            </div>
          )}

          {anyTracking && (
            <div className="map-panel" style={{ bottom: 16, top: 'auto', flexDirection: 'row', alignItems: 'center' }}>
              <Clock size={14} color="var(--accent)" />
              <span style={{ fontSize: 11, fontWeight: 700 }}>PATH WINDOW</span>
              <select style={{ padding: '4px 8px', fontFamily: 'var(--mono)', fontSize: 11, border: '1px solid var(--border)' }} value={trailDuration} onChange={e => handleTrailWindowUpdate(Number(e.target.value))}>
                <option value={30}>30 sec</option>
                <option value={60}>1 min</option>
                <option value={300}>5 min</option>
              </select>
            </div>
          )}

        </div>
      </div>

      {/* —————— RIGHT DASHBOARD SIDEBAR —————— */}
      {!isMapFullscreen && (
        <div className="dash-sidebar">

          <div className="dash-sys-stats">
            <div className="sys-stat-row">
              <span className="sys-stat-label">Total Personnel</span>
              <span className="sys-stat-val" style={{ color: 'var(--cyan)' }}>{safeCount}</span>
            </div>
            <div className="sys-stat-row">
              <span className="sys-stat-label">Gate IN</span>
              <span className="sys-stat-val" style={{ color: 'var(--success)' }}>{stats?.global_gate_in || 0}</span>
            </div>
            <div className="sys-stat-row">
              <span className="sys-stat-label">Gate OUT</span>
              <span className="sys-stat-val" style={{ color: 'var(--danger)' }}>{stats?.global_gate_out || 0}</span>
            </div>
            <div className="sys-stat-row">
              <span className="sys-stat-label">Active Alerts</span>
              <span className="sys-stat-val" style={{ color: safeAlerts > 0 ? 'var(--danger)' : 'var(--success)' }}>{safeAlerts}</span>
            </div>
          </div>

          {showDevTools && capturedCoord && (
            <div className="card" style={{ background: 'var(--accent)', color: '#000', padding: '8px 12px', fontWeight: 'bold', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span><Crosshair size={14} style={{ marginRight: 6 }} /> COORDINATES</span>
              <span>X: {capturedCoord.x} | Y: {capturedCoord.y}</span>
            </div>
          )}

          {showDevTools && (
            <div className="card">
              <div className="card-header"><span className="card-title"><Wrench size={12} /> DEV: BLIND SPOTS</span></div>
              <div style={{ padding: 12, display: 'flex', gap: 8, flexDirection: 'column' }}>
                <button
                  className={`btn ${isDrawingMode ? 'btn-danger' : 'btn-outline'}`}
                  onClick={() => setIsDrawingMode(!isDrawingMode)}
                >
                  {isDrawingMode ? 'STOP DRAWING' : 'DRAW BLIND SPOT'}
                </button>
                {blindSpots.length > 0 && (
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-outline" style={{ flex: 1 }} onClick={() => setBlindSpots(prev => prev.slice(0, -1))}>
                      UNDO LAST
                    </button>
                    <button className="btn btn-outline" style={{ flex: 1 }} onClick={() => setBlindSpots([])}>
                      CLEAR ALL
                    </button>
                  </div>
                )}
                {blindSpots.length > 0 && (
                  <button
                    className="btn btn-primary"
                    onClick={() => {
                      navigator.clipboard.writeText(JSON.stringify(blindSpots));
                      alert('Coordinates copied to clipboard! Please paste them in the chat.');
                    }}
                  >
                    COPY COORDS TO CLIPBOARD
                  </button>
                )}
              </div>
            </div>
          )}

          {zones.length > 1 && (
            <div className="card">
              <div className="card-header"><span className="card-title"><MapPin size={12} /> ZONES</span></div>
              <div style={{ padding: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {zones.map(z => (
                  <button key={z} onClick={() => setActiveTab(z)} className={`btn ${activeTab === z ? 'btn-primary' : 'btn-outline'}`} style={{ padding: '4px 10px', fontSize: 10 }}>
                    {z}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* CAMERA LIST */}
          <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="card-title"><Video size={12} /> CAMERAS</span>
              <div style={{ display: 'flex', alignItems: 'center', background: 'var(--bg-app)', padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>
                <Search size={10} style={{ color: 'var(--text-muted)', marginRight: 6 }} />
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-main)', fontSize: 11, outline: 'none', width: 80 }}
                />
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', padding: 8, gap: 4 }}>
              {searchedCameras.map(cam => {
                const isSel = activeCamera?.id === cam.id;
                const isTracking = trackingCameras[cam.id];
                const pCount = Array.isArray(stats?.cameras) ? stats.cameras.find(c => String(c.id) === String(cam.id))?.person_count : 0;
                return (
                  <div 
                    key={cam.id} 
                    onClick={() => handleSelectCamera(cam.id)}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px',
                      background: isSel ? 'var(--bg-app)' : 'var(--bg-surface)', border: `1px solid ${isSel ? 'var(--accent)' : 'var(--border)'}`,
                      borderRadius: 6, cursor: 'pointer', transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Video size={14} color={isSel ? 'var(--accent)' : 'var(--text-muted)'} />
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: isSel ? 'var(--accent)' : 'var(--text-main)' }}>{cam.name}</span>
                        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>#{cam.id}</span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {pCount > 0 && (
                        <span style={{ background: 'var(--cyan)', color: '#000', fontSize: 10, fontWeight: 800, padding: '2px 6px', borderRadius: 4 }}>
                          {pCount}
                        </span>
                      )}
                      <button
                        className={`btn ${isTracking ? 'btn-primary' : 'btn-outline'}`}
                        style={{ padding: '2px 6px', fontSize: 9 }}
                        onClick={(e) => { e.stopPropagation(); handleToggleTracking(cam.id); }}
                      >
                        {isTracking ? '● LIVE' : 'TRACK'}
                      </button>
                    </div>
                  </div>
                );
              })}
              {searchedCameras.length === 0 && (
                <div style={{ padding: 12, textAlign: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
                  No cameras found.
                </div>
              )}
            </div>
          </div>

        </div>
      )}

    </div>
  );
}




