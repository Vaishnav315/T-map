import { useLocation } from 'react-router-dom';
import { Wifi, WifiOff, Clock } from 'lucide-react';

export default function TopBar({ isBackendOffline, currentTime, isBlueprint, pageTitles = {} }) {
  const { pathname } = useLocation();
  const meta = pageTitles[pathname] || { title: 'TASL T-MAP', sub: 'Sentinel Intelligence Platform' };

  return (
    <header className="sentinel-header">
      <div className="header-left">
        <div className="header-page-title">{meta.title}</div>
        <div className="header-breadcrumb">{meta.sub}</div>
      </div>

      <div className="header-right">
        {isBlueprint && (
          <span className="tag tag-accent" style={{ padding: '6px 12px', fontSize: 11 }}>BLUEPRINT VIEW</span>
        )}

        <div className={`status-pill ${isBackendOffline ? 'offline' : 'live'}`}>
          <span className="status-dot" />
          {isBackendOffline ? 'PIPELINE OFFLINE' : 'ML PIPELINE LIVE'}
        </div>

        <div className="header-clock">
          <Clock size={14} />
          {currentTime.toLocaleTimeString('en-GB')}
        </div>
      </div>
    </header>
  );
}
