import React, { useState, useEffect, useRef } from 'react';
import { BarChart3, Download, Map, Activity, Clock, ShieldAlert } from 'lucide-react';

export default function DataDashboard({ backendUrl }) {
  const [telemetry, setTelemetry] = useState([]);
  const [loading, setLoading] = useState(true);
  const canvasRef = useRef(null);

  useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/telemetry?hours=24`);
        if (res.ok) {
          const data = await res.json();
          setTelemetry(data);
        }
      } catch (err) {
        console.error("Failed to fetch telemetry:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchTelemetry();
    const id = setInterval(fetchTelemetry, 10000); // refresh every 10s
    return () => clearInterval(id);
  }, [backendUrl]);

  useEffect(() => {
    if (!canvasRef.current || telemetry.length === 0) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Dark grid background
    ctx.fillStyle = '#020B18';
    ctx.fillRect(0, 0, width, height);
    
    // Draw simple grid
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let i = 0; i < width; i += 40) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, height); ctx.stroke();
    }
    for (let i = 0; i < height; i += 40) {
      ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(width, i); ctx.stroke();
    }

    // Since we don't know the exact max width/height of coordinates, we normalize
    let maxX = 1920; 
    let maxY = 1080; 

    // Find actual max to scale if needed
    telemetry.forEach(point => {
        if (point.x_pos > maxX) maxX = point.x_pos;
        if (point.y_pos > maxY) maxY = point.y_pos;
    });
    
    // Draw heatmap points
    telemetry.forEach(point => {
      const x = (point.x_pos / maxX) * width;
      const y = (point.y_pos / maxY) * height;

      // Draw a radial gradient for each point (heatmap effect)
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, 15);
      gradient.addColorStop(0, 'rgba(14, 165, 233, 0.4)'); // primary blue
      gradient.addColorStop(1, 'rgba(14, 165, 233, 0)');
      
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, 15, 0, Math.PI * 2);
      ctx.fill();
    });

  }, [telemetry]);

  const handleExportCSV = () => {
    if (telemetry.length === 0) return;
    const headers = ['ID', 'Timestamp', 'Camera ID', 'Track ID', 'X Pos', 'Y Pos', 'Tenant ID'];
    const rows = telemetry.map(t => [
      t.id, t.timestamp, t.camera_id, t.track_id, t.x_pos, t.y_pos, t.tenant_id
    ]);
    const csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "telemetry_export.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="page-container" style={{ padding: '24px', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '24px', fontWeight: 800, color: '#F8FAFC', margin: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
            <BarChart3 size={28} color="var(--accent)" /> AI ANALYTICS DASHBOARD
          </h2>
          <div style={{ color: '#94A3B8', fontSize: '14px', marginTop: '4px' }}>
            Historical trends, heatmaps, and worker density reports
          </div>
        </div>
        <button className="btn btn-primary" onClick={handleExportCSV} style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Download size={16} /> EXPORT CSV
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px', marginBottom: '24px' }}>
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ color: '#94A3B8', fontSize: '12px', fontWeight: 700, marginBottom: '8px', display: 'flex', alignItems: 'center', gap: 6 }}><Map size={14}/> TOTAL DATA POINTS</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#F8FAFC' }}>{telemetry.length}</div>
        </div>
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ color: '#94A3B8', fontSize: '12px', fontWeight: 700, marginBottom: '8px', display: 'flex', alignItems: 'center', gap: 6 }}><Clock size={14}/> TIME RANGE</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#F8FAFC' }}>Last 24h</div>
        </div>
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ color: '#94A3B8', fontSize: '12px', fontWeight: 700, marginBottom: '8px', display: 'flex', alignItems: 'center', gap: 6 }}><Activity size={14}/> ACTIVE CAMERAS</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#F8FAFC' }}>
            {new Set(telemetry.map(t => t.camera_id)).size}
          </div>
        </div>
      </div>

      <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="card-header">
          <span className="card-title">WORKER DENSITY HEATMAP</span>
          <span className="tag tag-info">LIVE</span>
        </div>
        <div style={{ padding: '20px', background: '#020B18', display: 'flex', justifyContent: 'center' }}>
          {loading ? (
            <div style={{ color: '#94A3B8', padding: '100px' }}>Loading telemetry...</div>
          ) : telemetry.length === 0 ? (
            <div style={{ color: '#94A3B8', padding: '100px' }}>No telemetry data found.</div>
          ) : (
            <div style={{ position: 'relative', width: '100%', maxWidth: '900px', aspectRatio: '16/9', border: '1px solid #1e293b' }}>
                <canvas 
                    ref={canvasRef} 
                    width={900} 
                    height={506} 
                    style={{ width: '100%', height: '100%', display: 'block' }} 
                />
                <div style={{ position: 'absolute', bottom: 12, right: 12, background: 'rgba(0,0,0,0.8)', padding: '4px 8px', fontSize: '10px', color: '#FFF', fontFamily: 'var(--mono)' }}>
                  Normalizing to 1920x1080 bounds
                </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
