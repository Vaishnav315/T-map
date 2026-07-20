import React, { useState, useEffect } from 'react';
import {
  Server, Database, Wifi, Upload, RefreshCw, Trash2,
  CheckCircle, AlertCircle, Clock, Plus, ChevronRight,
  Shield, Users, BarChart3, Globe, Loader2, X, Webhook, Key
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useAuth } from '../utils/AuthContext';

// ── Tab definitions ────────────────────────────────────────────────────────────
const TABS = [
  { id: 'integrations', label: 'Camera Integrations' },
  { id: 'account',      label: 'Account & Roles' },
  { id: 'tenant',       label: 'Organization' },
  { id: 'security',     label: 'Security' },
  { id: 'webhooks',     label: 'Webhooks & APIs' },
];

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    active:     { cls: 'active',  icon: <CheckCircle size={10} />, label: 'Active' },
    connected:  { cls: 'active',  icon: <CheckCircle size={10} />, label: 'Connected' },
    syncing:    { cls: 'pending', icon: <Loader2 size={10} className="sentineliq-spin" />, label: 'Syncing' },
    pending:    { cls: 'pending', icon: <Clock size={10} />,       label: 'Pending' },
    discovered: { cls: 'pending', icon: <Wifi size={10} />,        label: 'Discovered' },
    error:      { cls: 'error',   icon: <AlertCircle size={10} />, label: 'Error' },
  };
  const { cls, icon, label } = map[status] || map.pending;
  return (
    <span className={`integration-status ${cls}`}>
      {icon} {label}
    </span>
  );
}

// ── RTSP Bulk Import Form ──────────────────────────────────────────────────────
function RtspImportForm({ onDone }) {
  const [name, setName]   = useState('');
  const [raw, setRaw]     = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleImport = async () => {
    setError('');
    let cameras;
    try {
      cameras = JSON.parse(raw);
      if (!Array.isArray(cameras)) throw new Error('Must be a JSON array.');
    } catch (e) {
      setError('Invalid JSON. Expected an array of camera objects.');
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch('/api/integrations/rtsp-import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, cameras }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || 'Import failed.');
      }
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="integration-form">
      <div className="integration-field">
        <label className="integration-label">Integration Name</label>
        <input className="integration-input" value={name} onChange={e => setName(e.target.value)}
          placeholder="e.g. Plant Floor Zone A" />
      </div>
      <div className="integration-field">
        <label className="integration-label">
          Camera List (JSON array)
        </label>
        <textarea
          className="integration-input"
          style={{ minHeight: 120, resize: 'vertical', fontFamily: 'var(--mono)', fontSize: 11 }}
          value={raw}
          onChange={e => setRaw(e.target.value)}
          placeholder={`[\n  {"name": "Gate Cam 1", "rtsp_url": "rtsp://user:pass@192.168.1.10/stream", "area": "Main Gate"},\n  {"name": "Line A Cam", "rtsp_url": "rtsp://user:pass@192.168.1.11/stream", "area": "Production"}\n]`}
        />
      </div>
      {error && <div className="sentineliq-login-error" style={{ margin: 0 }}><AlertCircle size={12} />{error}</div>}
      <button
        className="btn btn-primary"
        onClick={handleImport}
        disabled={loading || !name || !raw}
        style={{ width: 'fit-content' }}
      >
        {loading ? <><Loader2 size={12} className="sentineliq-spin" /> Importing…</> : <><Upload size={12} /> Import Cameras</>}
      </button>
    </div>
  );
}

// ── ONVIF Discovery Form ───────────────────────────────────────────────────────
function OnvifDiscoveryForm({ onDone }) {
  const [name, setName]     = useState('');
  const [subnet, setSubnet] = useState('');
  const [user, setUser]     = useState('admin');
  const [pass, setPass]     = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError]   = useState('');

  const handleDiscover = async () => {
    setError(''); setResult(null);
    setLoading(true);
    try {
      const res = await apiFetch('/api/integrations/onvif-discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, subnet, username: user, password: pass }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Discovery failed.');
      setResult(d);
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="integration-form">
      <div className="integration-field">
        <label className="integration-label">Integration Name</label>
        <input className="integration-input" value={name} onChange={e => setName(e.target.value)}
          placeholder="e.g. Building A ONVIF Scan" />
      </div>
      <div className="integration-row">
        <div className="integration-field">
          <label className="integration-label">Subnet (first 3 octets)</label>
          <input className="integration-input" value={subnet} onChange={e => setSubnet(e.target.value)}
            placeholder="192.168.1" />
        </div>
        <div className="integration-field">
          <label className="integration-label">ONVIF Port</label>
          <input className="integration-input" type="number" defaultValue={80} readOnly />
        </div>
      </div>
      <div className="integration-row">
        <div className="integration-field">
          <label className="integration-label">Camera Username</label>
          <input className="integration-input" value={user} onChange={e => setUser(e.target.value)} />
        </div>
        <div className="integration-field">
          <label className="integration-label">Camera Password</label>
          <input className="integration-input" type="password" value={pass} onChange={e => setPass(e.target.value)} />
        </div>
      </div>
      {error && <div className="sentineliq-login-error" style={{ margin: 0 }}><AlertCircle size={12} />{error}</div>}
      {result && (
        <div className="sentineliq-login-success" style={{ margin: 0 }}>
          <CheckCircle size={12} /> Found {result.total_found} device(s) on {subnet}.0/24
        </div>
      )}
      <button
        className="btn btn-primary"
        onClick={handleDiscover}
        disabled={loading || !name || !subnet}
        style={{ width: 'fit-content' }}
      >
        {loading ? <><Loader2 size={12} className="sentineliq-spin" /> Scanning network…</> : <><Wifi size={12} /> Start ONVIF Scan</>}
      </button>
    </div>
  );
}

// ── DB Connection Form ─────────────────────────────────────────────────────────
function DbConnectionForm({ onDone }) {
  const [form, setForm] = useState({
    name: '', db_type: 'postgresql', host: '', port: 5432,
    database: '', username: '', password: '', table_name: 'cameras'
  });
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState('');
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleConnect = async () => {
    setError('');
    setLoading(true);
    try {
      const res = await apiFetch('/api/integrations/db-connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, port: Number(form.port) }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Connection failed.');
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="integration-form">
      <div className="integration-row">
        <div className="integration-field">
          <label className="integration-label">Integration Name</label>
          <input className="integration-input" value={form.name} onChange={e => set('name', e.target.value)}
            placeholder="e.g. Hikvision VMS DB" />
        </div>
        <div className="integration-field">
          <label className="integration-label">DB Type</label>
          <select className="integration-input" value={form.db_type} onChange={e => set('db_type', e.target.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL / MariaDB</option>
            <option value="mssql">SQL Server</option>
            <option value="sqlite">SQLite</option>
          </select>
        </div>
      </div>
      <div className="integration-row">
        <div className="integration-field">
          <label className="integration-label">Host / IP</label>
          <input className="integration-input" value={form.host} onChange={e => set('host', e.target.value)}
            placeholder="192.168.1.100" />
        </div>
        <div className="integration-field">
          <label className="integration-label">Port</label>
          <input className="integration-input" type="number" value={form.port}
            onChange={e => set('port', e.target.value)} />
        </div>
      </div>
      <div className="integration-row">
        <div className="integration-field">
          <label className="integration-label">Database Name</label>
          <input className="integration-input" value={form.database} onChange={e => set('database', e.target.value)}
            placeholder="vms_database" />
        </div>
        <div className="integration-field">
          <label className="integration-label">Camera Table</label>
          <input className="integration-input" value={form.table_name} onChange={e => set('table_name', e.target.value)} />
        </div>
      </div>
      <div className="integration-row">
        <div className="integration-field">
          <label className="integration-label">Username</label>
          <input className="integration-input" value={form.username} onChange={e => set('username', e.target.value)} />
        </div>
        <div className="integration-field">
          <label className="integration-label">Password</label>
          <input className="integration-input" type="password" value={form.password}
            onChange={e => set('password', e.target.value)} />
        </div>
      </div>
      {error && <div className="sentineliq-login-error" style={{ margin: 0 }}><AlertCircle size={12} />{error}</div>}
      <button
        className="btn btn-primary"
        onClick={handleConnect}
        disabled={loading || !form.name || !form.host || !form.database}
        style={{ width: 'fit-content' }}
      >
        {loading ? <><Loader2 size={12} className="sentineliq-spin" /> Connecting…</> : <><Database size={12} /> Connect Database</>}
      </button>
    </div>
  );
}

// ── Integrations Tab ──────────────────────────────────────────────────────────
function IntegrationsTab() {
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openCard, setOpenCard] = useState(null); // 'rtsp' | 'onvif' | 'db' | null

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/integrations/');
      if (res.ok) {
        const d = await res.json();
        setIntegrations(d.integrations || []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (id) => {
    if (!confirm('Remove this integration?')) return;
    await apiFetch(`/api/integrations/${id}`, { method: 'DELETE' });
    load();
  };

  const handleSync = async (id) => {
    await apiFetch(`/api/integrations/${id}/sync`, { method: 'POST' });
    load();
  };

  return (
    <div className="settings-section">
      {/* Add New Integration cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
        {/* RTSP Bulk Import */}
        <div className="integration-card">
          <div className="integration-card-header">
            <div className="integration-icon"><Upload size={18} /></div>
            <div>
              <div className="integration-title">Bulk RTSP Import</div>
              <div className="integration-desc">Import a JSON list of camera RTSP URLs</div>
            </div>
          </div>
          <button className="btn btn-outline" style={{ fontSize: 11 }}
            onClick={() => setOpenCard(openCard === 'rtsp' ? null : 'rtsp')}>
            {openCard === 'rtsp' ? <X size={11} /> : <Plus size={11} />}
            {openCard === 'rtsp' ? ' Close' : ' Add Cameras'}
          </button>
          {openCard === 'rtsp' && <RtspImportForm onDone={() => { setOpenCard(null); load(); }} />}
        </div>

        {/* ONVIF Discovery */}
        <div className="integration-card">
          <div className="integration-card-header">
            <div className="integration-icon"><Wifi size={18} /></div>
            <div>
              <div className="integration-title">ONVIF Auto-Discovery</div>
              <div className="integration-desc">Scan your network subnet for ONVIF cameras</div>
            </div>
          </div>
          <button className="btn btn-outline" style={{ fontSize: 11 }}
            onClick={() => setOpenCard(openCard === 'onvif' ? null : 'onvif')}>
            {openCard === 'onvif' ? <X size={11} /> : <Wifi size={11} />}
            {openCard === 'onvif' ? ' Close' : ' Scan Network'}
          </button>
          {openCard === 'onvif' && <OnvifDiscoveryForm onDone={() => { setOpenCard(null); load(); }} />}
        </div>

        {/* Database Connect */}
        <div className="integration-card">
          <div className="integration-card-header">
            <div className="integration-icon"><Database size={18} /></div>
            <div>
              <div className="integration-title">VMS Database Connect</div>
              <div className="integration-desc">Connect your existing CCTV management system DB</div>
            </div>
          </div>
          <button className="btn btn-outline" style={{ fontSize: 11 }}
            onClick={() => setOpenCard(openCard === 'db' ? null : 'db')}>
            {openCard === 'db' ? <X size={11} /> : <Database size={11} />}
            {openCard === 'db' ? ' Close' : ' Connect DB'}
          </button>
          {openCard === 'db' && <DbConnectionForm onDone={() => { setOpenCard(null); load(); }} />}
        </div>
      </div>

      {/* Existing integrations list */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)' }}>
            Active Integrations ({integrations.length})
          </span>
          <button className="btn btn-outline" style={{ fontSize: 10 }} onClick={load} disabled={loading}>
            <RefreshCw size={10} className={loading ? 'sentineliq-spin' : ''} /> Refresh
          </button>
        </div>

        {loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>
            <Loader2 size={16} className="sentineliq-spin" style={{ marginBottom: 8 }} /><br />
            Loading integrations…
          </div>
        )}

        {!loading && integrations.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '24px 0', textAlign: 'center', borderTop: '1px solid var(--border)' }}>
            No integrations yet. Add cameras using one of the methods above.
          </div>
        )}

        <div className="integrations-list">
          {integrations.map((intg) => (
            <div key={intg.id} className="integration-list-item">
              <div>
                <div className="integration-list-name">{intg.name}</div>
                <div className="integration-list-meta">
                  {intg.integration_type.replace('_', ' ').toUpperCase()} · {intg.camera_count || 0} cameras
                  {intg.last_synced ? ` · Synced ${intg.last_synced}` : ''}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <StatusBadge status={intg.status} />
                <div className="integration-list-actions">
                  <button className="btn btn-outline" style={{ fontSize: 10, padding: '4px 8px' }}
                    onClick={() => handleSync(intg.id)} title="Re-sync">
                    <RefreshCw size={10} />
                  </button>
                  <button className="btn btn-outline" style={{ fontSize: 10, padding: '4px 8px', color: 'var(--danger)' }}
                    onClick={() => handleDelete(intg.id)} title="Remove">
                    <Trash2 size={10} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Account Tab ────────────────────────────────────────────────────────────────
function AccountTab() {
  const { user } = useAuth();
  const [tenantInfo, setTenantInfo] = useState(null);

  useEffect(() => {
    apiFetch('/api/saas/my-tenant').then(r => r.json()).then(setTenantInfo).catch(() => {});
  }, []);

  return (
    <div className="settings-section">
      <div className="integration-card">
        <div className="integration-card-header">
          <div className="integration-icon"><Users size={18} /></div>
          <div>
            <div className="integration-title">Your Account</div>
            <div className="integration-desc">Logged in operator details</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 4 }}>
          <div>
            <div className="integration-label">Username</div>
            <div style={{ fontSize: 13, color: 'var(--text-main)', fontWeight: 600, marginTop: 4 }}>{user?.username}</div>
          </div>
          <div>
            <div className="integration-label">Role</div>
            <div style={{ marginTop: 4 }}>
              <span className={`plan-badge ${user?.role === 'admin' ? 'enterprise' : user?.role === 'safety_manager' ? 'professional' : 'starter'}`}>
                {user?.role || 'viewer'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {tenantInfo && (
        <div className="integration-card">
          <div className="integration-card-header">
            <div className="integration-icon"><Globe size={18} /></div>
            <div>
              <div className="integration-title">{tenantInfo.name}</div>
              <div className="integration-desc">Your organization</div>
            </div>
            <span className={`plan-badge ${tenantInfo.plan}`} style={{ marginLeft: 'auto' }}>{tenantInfo.plan}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 4 }}>
            <div>
              <div className="integration-label">Users</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-main)', marginTop: 4 }}>
                {tenantInfo.usage?.user_count || 0}
              </div>
            </div>
            <div>
              <div className="integration-label">Cameras</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-main)', marginTop: 4 }}>
                {tenantInfo.usage?.camera_count || 0}
              </div>
            </div>
            <div>
              <div className="integration-label">Integrations</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-main)', marginTop: 4 }}>
                {tenantInfo.usage?.integrations || 0}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Security Tab ───────────────────────────────────────────────────────────────
function SecurityTab() {
  return (
    <div className="settings-section">
      <div className="integration-card">
        <div className="integration-card-header">
          <div className="integration-icon"><Shield size={18} /></div>
          <div>
            <div className="integration-title">Security Status</div>
            <div className="integration-desc">Platform security configuration</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
          {[
            { label: 'JWT Authentication',    status: 'active',  desc: 'RS256-compatible HS256 token signing' },
            { label: 'AES-256 Credentials',  status: 'active',  desc: 'Camera credentials encrypted at rest' },
            { label: 'HTTPS / TLS',           status: 'active',  desc: 'Configured via nginx + auto.crt' },
            { label: 'Rate Limiting',         status: 'active',  desc: '10 login attempts per 5-minute window' },
            { label: 'Evidence Auth',         status: 'active',  desc: 'Screenshots require valid JWT' },
            { label: 'RBAC Roles',            status: 'active',  desc: 'admin / safety_manager / viewer' },
            { label: 'SOC2 Certification',    status: 'pending', desc: 'Checklist in progress — contact us' },
          ].map(item => (
            <div key={item.label} className="integration-list-item" style={{ padding: '10px 14px' }}>
              <div>
                <div className="integration-list-name" style={{ fontSize: 12 }}>{item.label}</div>
                <div className="integration-list-meta">{item.desc}</div>
              </div>
              <StatusBadge status={item.status} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Webhooks & APIs Tab ────────────────────────────────────────────────────────
function WebhooksTab() {
  const [webhooks, setWebhooks] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newKey, setNewKey] = useState('');
  const [newWebhook, setNewWebhook] = useState({ name: '', endpoint_url: '', secret: '' });

  const loadData = async () => {
    setLoading(true);
    try {
      const [whRes, keyRes] = await Promise.all([
        apiFetch('/api/webhooks'),
        apiFetch('/api/keys')
      ]);
      
      if (whRes.ok) {
        setWebhooks(await whRes.json());
      } else {
        const err = await whRes.json();
        console.error("Webhooks error:", err);
        setWebhooks([]);
      }

      if (keyRes.ok) {
        setApiKeys(await keyRes.json());
      } else {
        const err = await keyRes.json();
        console.error("API Keys error:", err);
        setApiKeys([]);
      }
    } catch (e) {
      console.error(e);
      setWebhooks([]);
      setApiKeys([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleCreateWebhook = async () => {
    if (!newWebhook.name || !newWebhook.endpoint_url) return;
    await apiFetch('/api/webhooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newWebhook)
    });
    setNewWebhook({ name: '', endpoint_url: '', secret: '' });
    loadData();
  };

  const handleCreateKey = async () => {
    const name = prompt("Enter a name for the new API Key:");
    if (!name) return;
    const res = await apiFetch('/api/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const d = await res.json();
    if (d.success) {
      alert("Please copy your new API Key now. You won't be able to see it again:\n\n" + d.api_key);
      loadData();
    }
  };

  return (
    <div className="settings-section">
      <div className="integration-card">
        <div className="integration-card-header">
          <div className="integration-icon"><Key size={18} /></div>
          <div>
            <div className="integration-title">API Keys</div>
            <div className="integration-desc">Manage keys for External API access</div>
          </div>
          <button className="btn btn-outline" style={{ marginLeft: 'auto', fontSize: 11 }} onClick={handleCreateKey}>
            <Plus size={11} /> Create Key
          </button>
        </div>
        <div className="integrations-list" style={{ marginTop: 12 }}>
          {apiKeys.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 10, textAlign: 'center' }}>No API keys configured.</div>
          ) : apiKeys.map(k => (
            <div key={k.id} className="integration-list-item">
              <div>
                <div className="integration-list-name">{k.name}</div>
                <div className="integration-list-meta">Created: {k.created_at}</div>
              </div>
              <StatusBadge status={k.is_active ? 'active' : 'error'} />
            </div>
          ))}
        </div>
      </div>

      <div className="integration-card" style={{ marginTop: 16 }}>
        <div className="integration-card-header">
          <div className="integration-icon"><Webhook size={18} /></div>
          <div>
            <div className="integration-title">Webhooks</div>
            <div className="integration-desc">Push real-time alerts to ERP/HSE systems</div>
          </div>
        </div>
        <div className="integration-form" style={{ marginTop: 12 }}>
          <div className="integration-row">
            <div className="integration-field">
              <label className="integration-label">Webhook Name</label>
              <input className="integration-input" value={newWebhook.name} onChange={e => setNewWebhook({...newWebhook, name: e.target.value})} placeholder="e.g. HSE Slack Bot" />
            </div>
            <div className="integration-field">
              <label className="integration-label">Endpoint URL</label>
              <input className="integration-input" value={newWebhook.endpoint_url} onChange={e => setNewWebhook({...newWebhook, endpoint_url: e.target.value})} placeholder="https://..." />
            </div>
          </div>
          <div className="integration-field">
            <label className="integration-label">Secret (Optional - for signature validation)</label>
            <input className="integration-input" type="password" value={newWebhook.secret} onChange={e => setNewWebhook({...newWebhook, secret: e.target.value})} />
          </div>
          <button className="btn btn-primary" style={{ width: 'fit-content' }} onClick={handleCreateWebhook} disabled={!newWebhook.name || !newWebhook.endpoint_url}>
             Add Webhook
          </button>
        </div>
        
        <div className="integrations-list" style={{ marginTop: 12 }}>
          {webhooks.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 10, textAlign: 'center' }}>No webhooks configured.</div>
          ) : webhooks.map(w => (
            <div key={w.id} className="integration-list-item">
              <div>
                <div className="integration-list-name">{w.name}</div>
                <div className="integration-list-meta">{w.endpoint_url}</div>
              </div>
              <StatusBadge status={w.is_active ? 'active' : 'error'} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Settings() {
  const [activeTab, setActiveTab] = useState('integrations');

  return (
    <div className="settings-page">
      <div className="settings-header">
        <div className="settings-title">Settings</div>
        <div className="settings-subtitle">Manage integrations, account, and security configuration</div>
      </div>

      <div className="settings-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'integrations' && <IntegrationsTab />}
      {activeTab === 'account'      && <AccountTab />}
      {activeTab === 'tenant'       && <AccountTab />}
      {activeTab === 'security'     && <SecurityTab />}
      {activeTab === 'webhooks'     && <WebhooksTab />}
    </div>
  );
}
