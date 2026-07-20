import { ShieldCheck, Map, Camera, History, ShieldAlert, Wifi, WifiOff, FlaskConical, PanelLeftClose, PanelLeftOpen, Settings, BarChart3 } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const NAV = [
  { to: '/',             label: 'LIVE MAP',      icon: Map         },
  { to: '/ai-analytics', label: 'ORCHESTRATION', icon: Camera      },
  { to: '/data-dashboard', label: 'DASHBOARD',   icon: BarChart3   },
  { to: '/history',      label: 'HISTORY',       icon: History     },
  { to: '/alerts',       label: 'ALERTS',        icon: ShieldAlert },
  { to: '/test-center',  label: 'TESTING',       icon: FlaskConical},
  { to: '/settings',     label: 'SETTINGS',      icon: Settings    },
];

export default function Header({ isBackendOffline, unreadAlerts = 0, isCollapsed, toggleSidebar }) {
  const { pathname } = useLocation();

  return (
    <aside className={`sentinel-sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      {/* Logo mark */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon" style={{ background: 'linear-gradient(135deg, #0ea5e9, #00e5ff)' }}>
          <ShieldCheck size={20} color="#020B18" strokeWidth={2.5} />
        </div>
        <div className="sidebar-logo-text-wrap">
          <div className="sidebar-logo-text">SentinelIQ</div>
          <div className="sidebar-logo-sub">AI SAFETY PLATFORM</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="sidebar-nav-label">Main Menu</div>
        {NAV.map(({ to, label, icon: Icon }) => {
          const isActive = pathname === to;
          const badge = to === '/alerts' && unreadAlerts > 0 ? unreadAlerts : 0;
          return (
            <Link key={to} to={to} className={`sidebar-nav-item${isActive ? ' active' : ''}${to === '/test-center' ? ' hidden-on-mobile' : ''}`} title={label}>
              <div style={{ flexShrink: 0 }}><Icon size={18} strokeWidth={isActive ? 2.5 : 2} /></div>
              <span>{label}</span>
              {badge > 0 && !isCollapsed && (
                <span className="sidebar-nav-badge">{badge > 99 ? '99+' : badge}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Bottom — system status & toggle */}
      <div className="sidebar-bottom">
        <button className="sidebar-toggle-btn" onClick={toggleSidebar} title="Toggle Sidebar">
          {isCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
        <div className="sidebar-status-box" title={isBackendOffline ? 'SYSTEM OFFLINE' : 'SYSTEM ONLINE'}>
          {isBackendOffline
            ? <WifiOff size={16} color="var(--danger)" style={{ flexShrink: 0 }} />
            : <Wifi    size={16} color="var(--success)" style={{ flexShrink: 0 }} />
          }
          {!isCollapsed && (
            <div className="sidebar-status-text">
              {isBackendOffline ? 'SYSTEM OFFLINE' : 'SYSTEM ONLINE'}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
