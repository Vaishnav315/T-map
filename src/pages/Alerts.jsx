import React, { useState } from 'react';
import { AlertTriangle, ShieldAlert, Info, ShieldCheck, Filter, X, CheckCircle, Clock } from 'lucide-react';

const SEVERITY_META = {
  CRITICAL: { color: 'var(--danger)',  bg: 'rgba(239,68,68,0.06)',  icon: ShieldAlert },
  HIGH:     { color: 'var(--warning)', bg: 'rgba(245,158,11,0.06)', icon: AlertTriangle },
  WARNING:  { color: 'var(--warning)', bg: 'rgba(245,158,11,0.06)', icon: AlertTriangle },
  INFO:     { color: 'var(--info)',    bg: 'rgba(59,130,246,0.06)', icon: Info }
};

const VLM_STATUS_META = {
  PENDING:  { color: '#F59E0B', label: 'AI Analysing', icon: Clock },
  VERIFIED: { color: '#10B981', label: 'AI Verified',  icon: CheckCircle },
  CLEARED:  { color: '#64748B', label: 'Cleared',      icon: ShieldCheck },
};

const getSeverityMeta = (sev) => SEVERITY_META[sev?.toUpperCase()] || SEVERITY_META.INFO;
const getVlmMeta      = (st)  => VLM_STATUS_META[st?.toUpperCase()]  || VLM_STATUS_META.PENDING;

export default function Alerts({ alertLogs = [], onClearLogs, backendUrl = 'http://localhost:5000' }) {
  const [filter, setFilter] = useState('ALL');

  const filtered = filter === 'ALL'
    ? alertLogs
    : filter === 'PENDING'
      ? alertLogs.filter(a => (a.vlm_status || 'PENDING') === 'PENDING')
      : alertLogs.filter(a => a.severity?.toUpperCase() === filter);

  const stats = {
    critical: alertLogs.filter(a => a.severity?.toUpperCase() === 'CRITICAL').length,
    warnings: alertLogs.filter(a => ['WARNING','HIGH'].includes(a.severity?.toUpperCase())).length,
    pending:  alertLogs.filter(a => (a.vlm_status || 'PENDING') === 'PENDING').length,
    total:    alertLogs.length,
  };

  const handleDismiss = async (alertId) => {
    try {
      await fetch(`${backendUrl}/api/alert_logs/${alertId}`, { method: 'DELETE' });
    } catch (_) {}
  };

  const handleManualVerify = async (alertId) => {
    try {
      await fetch(`${backendUrl}/api/alert_logs/${alertId}/verify`, { method: 'POST' });
    } catch (_) {}
  };

  return (
    <div className="page-container">

      {/* Stat Row */}
      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-card-label">Critical</span>
          <span className="stat-card-value" style={{ color: 'var(--danger)' }}>{stats.critical}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">Warnings</span>
          <span className="stat-card-value" style={{ color: 'var(--warning)' }}>{stats.warnings}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">AI Pending</span>
          <span className="stat-card-value" style={{ color: '#F59E0B' }}>{stats.pending}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">Total</span>
          <span className="stat-card-value">{stats.total}</span>
        </div>
      </div>

      <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Filter Bar */}
        <div className="card-header" style={{ padding: '10px 16px', background: 'var(--bg-card)', flexShrink: 0, flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', width: '100%', overflowX: 'auto', whiteSpace: 'nowrap', paddingBottom: 4 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
              <Filter size={13} color="var(--text-muted)" />
              {['ALL', 'WARNING', 'CRITICAL', 'INFO', 'PENDING'].map(f => (
                <button
                  key={f}
                  className={`btn ${filter === f ? 'btn-primary' : 'btn-outline'}`}
                  style={{ padding: '4px 10px', fontSize: 10 }}
                  onClick={() => setFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>
            <div style={{ flex: 1 }}></div>
            <button
              className="btn btn-outline"
              style={{ padding: '4px 10px', fontSize: 10, borderColor: 'var(--danger)', color: 'var(--danger)', flexShrink: 0 }}
              onClick={onClearLogs}
            >
              Clear All
            </button>
          </div>
          <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-muted)' }}>
            {filtered.length} events
          </span>
        </div>

        {/* Alert List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', background: 'var(--bg-app)' }}>
          {filtered.length === 0 ? (
            <div className="empty-state">
              <ShieldCheck size={48} color="var(--success)" />
              <div className="empty-state-title">ALL PERIMETERS SECURE</div>
              <div className="empty-state-sub">No active threats detected.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {filtered.map(alert => {
                const sev     = getSeverityMeta(alert.severity);
                const SevIcon = sev.icon;
                const vlm     = getVlmMeta(alert.vlm_status);
                const VlmIcon = vlm.icon;

                return (
                  <div
                    key={alert.id}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      borderLeft: `4px solid ${sev.color}`,
                      
                      overflow: 'hidden',
                      boxShadow: '0 1px 4px rgba(0,0,0,0.05)',
                    }}
                  >
                    {/* Header */}
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '10px 14px', background: sev.bg,
                      borderBottom: '1px solid var(--border-light)'
                    }}>
                      <SevIcon size={14} color={sev.color} />
                      <span style={{ fontSize: 11, fontWeight: 800, color: sev.color, letterSpacing: 1 }}>
                        {alert.severity?.toUpperCase() || 'INFO'}
                      </span>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                        {alert.type || ''}
                      </span>

                      {/* VLM Status Badge */}
                      <span style={{
                        marginLeft: 'auto',
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontSize: 10, fontWeight: 700, color: vlm.color,
                        background: `${vlm.color}1a`,  padding: '2px 8px'
                      }}>
                        <VlmIcon size={10} />
                        {vlm.label}
                      </span>

                      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                        {alert.timestamp?.split(' ')[1] || alert.timestamp}
                      </span>
                    </div>

                    {/* Body */}
                    <div style={{ padding: '12px 14px', display: 'flex', gap: 12 }}>
                      {/* Evidence Thumbnail */}
                      {alert.evidence && (
                        <a
                          href={`${backendUrl}/evidence/${alert.evidence}`}
                          target="_blank" rel="noopener noreferrer"
                          style={{ flexShrink: 0, display: 'block', width: 84, height: 64,  overflow: 'hidden', border: '1px solid var(--border)' }}
                        >
                          <img
                            src={`${backendUrl}/evidence/${alert.evidence}`}
                            alt="Evidence"
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={e => { e.target.style.display = 'none'; }}
                          />
                        </a>
                      )}

                      {/* Text */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-body)', marginBottom: 4 }}>
                          {alert.details}
                        </div>

                        {alert.vlm_description && (
                          <div style={{
                            fontSize: 12, color: 'var(--text-muted)',
                            borderLeft: '2px solid var(--accent)', paddingLeft: 8,
                            marginTop: 6, fontStyle: 'italic', lineHeight: 1.4
                          }}>
                            {alert.vlm_description}
                          </div>
                        )}

                        {/* Footer Actions */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                          <span className="tag" style={{ background: 'var(--bg-app)', fontSize: 10 }}>
                            {alert.camera_name || `CAM-${alert.camera_id}`}
                          </span>

                          {/* Manual Verify â€” only show for PENDING alerts */}
                          {(!alert.vlm_status || alert.vlm_status === 'PENDING') && (
                            <button
                              className="btn btn-outline"
                              style={{ padding: '3px 8px', fontSize: 10, borderColor: '#10B981', color: '#10B981' }}
                              onClick={() => handleManualVerify(alert.id)}
                              title="Manually verify this alert"
                            >
                              âœ“ Verify
                            </button>
                          )}

                          {/* Dismiss */}
                          <button
                            className="btn btn-outline"
                            style={{ padding: '3px 8px', fontSize: 10, borderColor: 'var(--danger)', color: 'var(--danger)', marginLeft: 'auto' }}
                            onClick={() => handleDismiss(alert.id)}
                            title="Dismiss this alert"
                          >
                            <X size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 2 }} />
                            Dismiss
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

