import React, { useState } from 'react';
import { Database } from 'lucide-react';

export default function History({ 
  systemLogs = [], 
  vlmLogs = [], 
  gateEvents = [], 
  onClearLogs, 
  backendUrl = 'http://localhost:5001' 
}) {
  const [tab, setTab] = useState('system');

  const getActiveLogs = () => {
    if (tab === 'system') return systemLogs;
    if (tab === 'vlm') return vlmLogs;
    if (tab === 'gate') return gateEvents;
    return [];
  };

  const activeLogs = getActiveLogs();

  const handleClearTabLogs = async () => {
    try {
      if (tab === 'system') {
        await fetch(`${backendUrl}/api/logs/clear`, { method: 'POST' });
      } else if (tab === 'vlm') {
        await fetch(`${backendUrl}/api/vlm_logs/clear`, { method: 'POST' });
      }
      if (onClearLogs) {
        onClearLogs();
      }
    } catch (e) {
      console.error("Error clearing logs:", e);
    }
  };

  return (
    <div className="page-container">

      <div className="stat-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        <div className="stat-card">
          <span className="stat-card-label">System Logs</span>
          <span className="stat-card-value">{systemLogs.length}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">VLM Analysis</span>
          <span className="stat-card-value">{vlmLogs.length}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">Gate Events</span>
          <span className="stat-card-value">{gateEvents.length}</span>
        </div>
      </div>

      <div className="history-table-container">
                <div className="history-tabs" style={{ display: 'flex', overflowX: 'auto', whiteSpace: 'nowrap', gap: 8, paddingBottom: 4, alignItems: 'center' }}>
          <div className={`history-tab ${tab === 'system' ? 'active' : ''}`} onClick={() => setTab('system')} style={{ flexShrink: 0 }}>
            <Database size={14}/> SYSTEM TELEMETRY
          </div>
          <div className={`history-tab ${tab === 'vlm' ? 'active' : ''}`} onClick={() => setTab('vlm')} style={{ flexShrink: 0 }}>
            <Database size={14}/> VLM INFERENCE
          </div>
          <div className={`history-tab ${tab === 'gate' ? 'active' : ''}`} onClick={() => setTab('gate')} style={{ flexShrink: 0 }}>
            <Database size={14}/> GATE TRANSACTIONS
          </div>
        </div>
        
        <div style={{ padding: '8px 16px', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)' }}>{activeLogs.length} Records</span>
          <button 
            className="btn btn-outline" 
            style={{ padding: '4px 12px', fontSize: 10, borderColor: 'var(--danger)', color: 'var(--danger)' }}
            onClick={handleClearTabLogs}
          >
            CLEAR {tab.toUpperCase()} LOGS
          </button>
        </div>

        <div className="history-list">
          {activeLogs.length === 0 ? (
            <div className="empty-state">
              <Database size={48} color="var(--border-strong)" />
              <div className="empty-state-title">NO RECORDS FOUND</div>
              <div className="empty-state-sub">Archive is currently empty for this category.</div>
            </div>
          ) : (
            activeLogs.map(log => (
              <div key={log.id} className={`history-row ${tab === 'gate' ? 'gate-row' : ''}`}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 700, color: 'var(--text-main)' }}>
                    {log.timestamp?.split(' ')[1] || log.timestamp}
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                    {log.timestamp?.split(' ')[0]}
                  </span>
                </div>
                <div>
                  <span className="tag" style={{ background: 'var(--bg-card)' }}>
                    {tab === 'gate' 
                      ? (log.event_type === 'IN' ? 'GATE IN' : 'GATE OUT') 
                      : (log.camera_name || `CAM-${log.camera_id}`)}
                  </span>
                </div>
                {tab !== 'gate' && (
                  <div>
                    <span style={{ fontSize: 11, fontWeight: 800, color: log.severity === 'ERROR' ? 'var(--danger)' : 'var(--text-main)' }}>
                      {log.severity}
                    </span>
                  </div>
                )}
                {tab === 'gate' && (
                  <div>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                      Pos: [{log.leaflet_y?.toFixed(2)}, {log.leaflet_x?.toFixed(2)}]
                    </span>
                  </div>
                )}
                <div style={{ fontSize: 13, color: 'var(--text-body)' }}>
                  {tab === 'gate' ? 'Gate crossing transaction logged.' : log.details}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

    </div>
  );
}



