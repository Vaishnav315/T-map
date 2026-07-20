import React, { useState, useEffect, useCallback } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import './App.css';

import { MAP_LAYERS } from './constants/mapConfig';
import { API_BASE } from './utils/api';

import Header from './components/Layout/Header';
import TopBar from './components/Layout/TopBar';
import CameraModal from './components/Modal/CameraModal';

// Pages
import Dashboard from './pages/Dashboard';
import AIAnalytics from './pages/AIAnalytics';
import History from './pages/History';
import Alerts from './pages/Alerts';
import TestCenter from './pages/TestCenter';
import Settings from './pages/Settings';
import DataDashboard from './pages/DataDashboard';

import Login from './pages/Login';
import Signup from './pages/Signup';
import { useAuth } from './utils/AuthContext';
import { Navigate } from 'react-router-dom';

const INITIAL_CAMERAS = [
  { id: '27', name: 'P2 C1', coords: [17.2438281, 78.5407760], blueprint_coords: [386, 849], ip: '10.10.25.223', brand: 'ONVIF', area: 'Plant 2', percentage_x: 41.455, percentage_y: 29.922, viewing_angle: 90 },
  { id: '33', name: 'P3 A16', coords: [17.2439568, 78.5405590], blueprint_coords: [804, 346], ip: '10.10.25.226', brand: 'ONVIF', area: 'Plant 3', percentage_x: 16.895, percentage_y: 62.326, viewing_angle: 180 },
  { id: '35', name: 'P3 B16', coords: [17.2440603, 78.5414556], blueprint_coords: [898, 352], ip: '10.10.25.230', brand: 'ONVIF', area: 'Plant 3', percentage_x: 17.188, percentage_y: 69.612, viewing_angle: 270 },
  { id: '3', name: 'SECURITY IN', coords: [17.2444810, 78.5418086], blueprint_coords: [589, 955], ip: '10.10.25.205', brand: 'ONVIF', area: 'Perimeter/Logistics', percentage_x: 46.631, percentage_y: 45.659, viewing_angle: 0 },
];

function AppShell() {
  const [cameras, setCameras] = useState(INITIAL_CAMERAS);
  const [activeCamera, setActiveCamera] = useState(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  // FIX 1: Set initial view to 'blueprint' so blueprint graphics render immediately
  const [mapLayer, setMapLayer] = useState('blueprint');
  const [showLayerMenu, setShowLayerMenu] = useState(false);
  const [detectFacesActive, setDetectFacesActive] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [backendUrl] = useState(API_BASE);       // uses VITE_API_URL in production
  const [pollingInterval] = useState(3000);       // 3s polling — reasonable for dashboard data
  const [isBackendOffline, setIsBackendOffline] = useState(false);
  const [capturedCoord, setCapturedCoord] = useState(null);

  // Advanced path trail states
  const [selectedWorkerId, setSelectedWorkerId] = useState(null);
  const [trailDuration, setTrailDuration] = useState(60);
  const [isSyncingSettings, setIsSyncingSettings] = useState(false);

  // Tracking states loaded dynamically (initial off-state keys mapped)
  const [trackingCameras, setTrackingCameras] = useState({
    '28': false, '27': false, '33': false, '35': false, '3': false
  });
  const [securityGateCounting, setSecurityGateCounting] = useState({});
  const [stats, setStats] = useState({ person_count: 0, active_alerts: 0, cameras: [] });
  const [alertLogs, setAlertLogs] = useState([]);
  const [systemLogs, setSystemLogs] = useState([]);
  const [vlmLogs, setVlmLogs] = useState([]);
  const [gateEvents, setGateEvents] = useState([]);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [activeTab, setActiveTab] = useState('All');
  
  // Toast Notification State
  const [toastAlert, setToastAlert] = useState(null);

  const isBlueprint = MAP_LAYERS[mapLayer]?.isBlueprint ?? true;
  const zones = ['All', ...new Set(cameras.map(c => c.area).filter(Boolean))];
  const filteredCameras = activeTab === 'All'
    ? cameras
    : cameras.filter(cam => cam.area === activeTab);

  // Only render cameras with layout coords mapped on the simple CRS blueprint canvas map
  const mapCameras = filteredCameras.filter(cam => isBlueprint ? cam.blueprint_coords : cam.coords);

  // Load cameras layout configuration dynamically on mount
  const loadConfig = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${backendUrl}/api/config/cameras`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setCameras(data);
        const initialTracking = {};
        data.forEach(cam => { initialTracking[cam.id] = false; });
        setTrackingCameras(initialTracking);
      }
    } catch (err) {
      console.error('Failed loading camera configurations:', err);
    }
  }, [backendUrl]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    const t = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Sync state stats and alerts pipelines
  useEffect(() => {
    let alive = true;
    const token = () => localStorage.getItem('token');
    const authHeader = () => token() ? { Authorization: `Bearer ${token()}` } : {};

    const poll = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/stats`, { headers: authHeader() });
        if (res.ok) {
          const data = await res.json();
          if (alive) {
            setStats({
              person_count: data.person_count || 0,
              active_alerts: data.active_alerts || 0,
              unread_alerts: data.unread_alerts || 0,
              cameras: data.cameras || [],
              global_gate_in: data.global_gate_in || 0,
              global_gate_out: data.global_gate_out || 0,
              global_tracks: data.global_tracks || []
            });
            setIsBackendOffline(false);
          }
        } else {
          throw new Error();
        }

        const [systemRes, alertRes, vlmRes, gateRes, unreadRes] = await Promise.all([
          fetch(`${backendUrl}/api/logs`,        { headers: authHeader() }),
          fetch(`${backendUrl}/api/alert_logs`,  { headers: authHeader() }),
          fetch(`${backendUrl}/api/vlm_logs`,    { headers: authHeader() }),
          fetch(`${backendUrl}/api/gate_events`, { headers: authHeader() }),
          fetch(`${backendUrl}/api/alerts/unread`, { headers: authHeader() }),
        ]);

        if (alive) {
          if (systemRes.ok) setSystemLogs(await systemRes.json());
          if (alertRes.ok)  setAlertLogs(await alertRes.json());
          if (vlmRes.ok)    setVlmLogs(await vlmRes.json());
          if (gateRes.ok)   setGateEvents(await gateRes.json());
          if (unreadRes.ok) {
            const d = await unreadRes.json();
            setUnreadAlerts(d.count || 0);
          }
        }
      } catch {
        if (alive) setIsBackendOffline(true);
      }
    };
    poll();
    const id = setInterval(poll, pollingInterval);
    return () => { alive = false; clearInterval(id); };
  }, [backendUrl, pollingInterval]);

  // Setup SSE for real-time alerts
  useEffect(() => {
    const eventSource = new EventSource(`${backendUrl}/api/alerts/stream`);
    
    eventSource.onmessage = (event) => {
        try {
            const newAlert = JSON.parse(event.data);
            if (newAlert.type === 'CLEAR_ALL') {
                setAlertLogs([]);
                setUnreadAlerts(0);
                if (typeof window.onTestAlertReceived === 'function') {
                    window.onTestAlertReceived({ type: 'CLEAR_ALL' });
                }
                return;
            }
            // Single alert dismissed by operator
            if (newAlert.type === 'DISMISS') {
                setAlertLogs(prev => prev.filter(log => log.id !== newAlert.id));
                return;
            }
            if (newAlert.is_update) {
                setAlertLogs(prev => prev.map(log => log.id === newAlert.id ? { ...log, ...newAlert } : log));
                if (newAlert.camera_id && newAlert.camera_id.startsWith('test_')) {
                    if (typeof window.onTestAlertReceived === 'function') window.onTestAlertReceived(newAlert);
                }
                
                // Show toast when VLM verifies an alert
                if (newAlert.vlm_status === 'VERIFIED') {
                    setToastAlert(newAlert);
                    setTimeout(() => setToastAlert(null), 5000);
                }
            } else {
                setAlertLogs(prev => [newAlert, ...prev].slice(0, 200));
                setUnreadAlerts(prev => prev + 1);
                
                if (newAlert.camera_id && newAlert.camera_id.startsWith('test_')) {
                    if (typeof window.onTestAlertReceived === 'function') window.onTestAlertReceived(newAlert);
                }
            }
        } catch (e) {
            // Heartbeat or parse error
        }
    };
    
    return () => eventSource.close();
  }, [backendUrl]);

  const handleToggleTracking = async (camId) => {
    const newState = !trackingCameras[camId];
    setTrackingCameras(prev => ({ ...prev, [camId]: newState }));
    try {
      await fetch(`${backendUrl}/api/map_tracking/${camId}/${newState ? 'on' : 'off'}`, { method: 'POST' });
    } catch (e) {
      console.error(`Tracking toggle failed for ${camId}:`, e);
    }
  };

  const handleToggleSecurityGateCounting = async (camId) => {
    const newState = !securityGateCounting[camId];
    setSecurityGateCounting(prev => ({ ...prev, [camId]: newState }));
    try {
      await fetch(`${backendUrl}/api/gate_counting/${camId}/${newState ? 'on' : 'off'}`, { method: 'POST' });
    } catch (e) {
      console.error(`Security Gate counting toggle failed for cam ${camId}:`, e);
    }
  };

  const handleTrailWindowUpdate = async (seconds) => {
    setIsSyncingSettings(true);
    setTrailDuration(seconds);
    try {
      await fetch(`${backendUrl}/api/trail_settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: seconds })
      });
    } catch (err) {
      console.warn('[CONFIG UPSTREAM] Sub-endpoint missing, running locally.');
    } finally {
      setIsSyncingSettings(false);
    }
  };

  const handleSelectCamera = (camId) => {
    const cam = cameras.find(c => c.id === camId);
    if (cam) {
      setSelectedCoords(isBlueprint ? cam.blueprint_coords : cam.coords);
      setActiveCamera(cam);
    }
  };

  const handleCloseCamera = () => {
    setActiveCamera(null);
    setIsMaximized(false);
    setDetectFacesActive(false);
  };

  const handleLayerSwitch = (key) => {
    setMapLayer(key);
    setShowLayerMenu(false);
    setSelectedCoords(null);
    setCapturedCoord(null);
  };

  const handleClearLogs = async () => {
    setSystemLogs([]);
    setAlertLogs([]);
    setVlmLogs([]);
    setGateEvents([]);
    setUnreadAlerts(0);
    try {
      await Promise.all([
        fetch(`${backendUrl}/api/logs/clear`, { method: 'POST' }),
        fetch(`${backendUrl}/api/alert_logs/clear`, { method: 'POST' }),
        fetch(`${backendUrl}/api/vlm_logs/clear`, { method: 'POST' }),
        fetch(`${backendUrl}/api/gate_events/clear`, { method: 'POST' })
      ]);
    } catch (err) {
      console.error("Failed to clear logs:", err);
    }
  };

  const blueprintAccent = '#00e5ff';
  const satelliteAccent = '#3b82f6';
  const accent = isBlueprint ? blueprintAccent : satelliteAccent;

  const PAGE_TITLES = {
    '/':             { title: 'Live Map Dashboard', sub: 'Real-time facility monitoring' },
    '/ai-analytics': { title: 'AI Analytics',       sub: 'Inference pipeline management' },
    '/history':      { title: 'Event History',       sub: 'System logs & gate events' },
    '/alerts':       { title: 'Alert Center',        sub: 'Security & safety events' },
    '/test-center':  { title: 'Test Center',         sub: 'Stream & system diagnostics' },
    '/settings':     { title: 'Settings',            sub: 'Integrations & configuration' },
  };

  return (
    <div className="sentinel-app">
      {/* ── SIDEBAR ── */}
      <Header
        isBlueprint={isBlueprint} accent={accent} blueprintAccent={blueprintAccent}
        currentTime={currentTime} isBackendOffline={isBackendOffline}
        unreadAlerts={unreadAlerts} pageTitles={PAGE_TITLES}
        isCollapsed={isCollapsed} toggleSidebar={() => setIsCollapsed(!isCollapsed)}
      />

      {/* ── MAIN CONTENT ── */}
      <main className="sentinel-main">
        <TopBar
          isBackendOffline={isBackendOffline}
          currentTime={currentTime}
          isBlueprint={isBlueprint}
          accent={accent}
          pageTitles={PAGE_TITLES}
        />
        <div className="sentinel-workspace">
          <Routes>
            <Route path="/" element={
              <Dashboard 
                accent={accent} blueprintAccent={blueprintAccent} satelliteAccent={satelliteAccent}
                isBackendOffline={isBackendOffline} stats={stats} filteredCameras={filteredCameras}
                activeCamera={activeCamera} handleSelectCamera={handleSelectCamera} isBlueprint={isBlueprint}
                capturedCoord={capturedCoord} setCapturedCoord={setCapturedCoord} activeTab={activeTab}
                setActiveTab={setActiveTab} zones={zones} alertLogs={alertLogs} mapLayer={mapLayer}
                showLayerMenu={showLayerMenu} setShowLayerMenu={setShowLayerMenu} handleLayerSwitch={handleLayerSwitch}
                trackingCameras={trackingCameras} handleToggleTracking={handleToggleTracking} selectedCoords={selectedCoords}
                securityGateCounting={securityGateCounting} handleToggleSecurityGateCounting={handleToggleSecurityGateCounting}
                mapCameras={mapCameras} trailDuration={trailDuration} handleTrailWindowUpdate={handleTrailWindowUpdate}
                isSyncingSettings={isSyncingSettings} selectedWorkerId={selectedWorkerId} setSelectedWorkerId={setSelectedWorkerId}
                unreadAlerts={unreadAlerts}
              />
            } />
            <Route path="/ai-analytics" element={
              <AIAnalytics
                cameras={cameras} isBackendOffline={isBackendOffline} stats={stats}
                trackingCameras={trackingCameras} backendUrl={backendUrl}
              />
            } />
            <Route path="/history" element={<History systemLogs={systemLogs} vlmLogs={vlmLogs} gateEvents={gateEvents} onClearLogs={handleClearLogs} />} />
            <Route path="/alerts" element={<Alerts alertLogs={alertLogs} onClearLogs={handleClearLogs} backendUrl={backendUrl} />} />
            <Route path="/test-center" element={<TestCenter backendUrl={backendUrl} />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/data-dashboard" element={<DataDashboard backendUrl={backendUrl} />} />
          </Routes>
        </div>
      </main>

      {/* Side Toast Notification */}
      {toastAlert && (
        <div style={{
          position: 'fixed', top: 24, right: 24, zIndex: 9999,
          background: '#0F172A', borderLeft: '4px solid var(--danger)',
          borderRadius: 8, padding: '14px 18px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          animation: 'slideIn 0.3s ease-out',
          maxWidth: 360, minWidth: 280,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Sparkles size={13} color="var(--danger)" />
              <span style={{ fontSize: 10, fontWeight: 800, color: 'var(--danger)', letterSpacing: 1, textTransform: 'uppercase' }}>
                VLM Verified Alert
              </span>
            </div>
            <button
              onClick={() => setToastAlert(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', padding: 0, lineHeight: 1 }}
            >
              ✕
            </button>
          </div>
          <div style={{ fontSize: 13, color: '#F8FAFC', fontWeight: 600, marginBottom: 4 }}>
            {toastAlert.type || toastAlert.title || 'Security Alert'}
          </div>
          {toastAlert.vlm_description && (
            <div style={{ fontSize: 12, color: '#94A3B8', lineHeight: 1.4 }}>
              {toastAlert.vlm_description}
            </div>
          )}
          <div style={{ fontSize: 10, color: '#475569', marginTop: 6, fontFamily: 'var(--mono)' }}>
            {toastAlert.camera_name || `CAM-${toastAlert.camera_id}`} • {toastAlert.timestamp?.split(' ')[1] || ''}
          </div>
        </div>
      )}

      <CameraModal
        activeCamera={activeCamera} handleCloseCamera={handleCloseCamera}
        isMaximized={isMaximized} setIsMaximized={setIsMaximized}
        detectFacesActive={detectFacesActive} setDetectFacesActive={setDetectFacesActive}
        backendUrl={backendUrl} isBackendOffline={isBackendOffline}
        stats={stats} accent={accent} satelliteAccent={satelliteAccent}
        setSelectedWorkerId={setSelectedWorkerId} selectedWorkerId={selectedWorkerId}
        isTrackingOnDashboard={activeCamera ? !!trackingCameras[activeCamera.id] : false}
      />
    </div>
  );
}

function App() {
  const { token, loading } = useAuth();
  
  if (loading) {
    return <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-app)', color: 'var(--text-main)' }}>Loading TASL Sentinel...</div>;
  }

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="*" element={token ? <AppShell /> : <Navigate to="/login" />} />
    </Routes>
  );
}

export default App;