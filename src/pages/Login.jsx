import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../utils/AuthContext';
import { apiFetch } from '../utils/api';
import { ShieldCheck, Eye, EyeOff, Loader2, AlertCircle } from 'lucide-react';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await apiFetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username, password }),
      });

      if (res.ok) {
        const data = await res.json();
        login(data.access_token);
        navigate('/');
      } else {
        if (res.status === 429) {
          setError('Too many failed attempts. Please wait 5 minutes before trying again.');
        } else {
          const data = await res.json();
          setError(data.detail || 'Invalid credentials');
        }
      }
    } catch (err) {
      setError('Connection failed. Please check if the server is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-split-container">
      {/* Left Side: Industrial Image / Branding */}
      <div className="auth-left">
        <div className="auth-left-content">
          <div className="auth-logo">
            <ShieldCheck size={48} color="var(--primary)" strokeWidth={1.5} />
          </div>
          <h1>SentinelIQ</h1>
          <h2>Industrial AI Safety Intelligence</h2>
          <p>
            Real-time digital twin monitoring, multi-camera re-identification, 
            and 4-tier VLM hazard verification. Protect your workforce with 
            deterministic AI.
          </p>
        </div>
      </div>

      {/* Right Side: Login Form */}
      <div className="auth-right">
        <div className="auth-form-container">
          <div className="auth-form-header">
            <h3>Operator Login</h3>
            <p>Enter your credentials to access the facility dashboard.</p>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="auth-input-group">
              <label>Username</label>
              <input
                type="text"
                className="auth-input"
                placeholder="e.g. admin_operator"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={loading}
              />
            </div>

            <div className="auth-input-group">
              <label>Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPass ? 'text' : 'password'}
                  className="auth-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                />
                <button
                  type="button"
                  className="auth-pass-toggle"
                  onClick={() => setShowPass(!showPass)}
                  tabIndex="-1"
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="auth-error">
                <AlertCircle size={14} />
                <span>{error}</span>
              </div>
            )}

            <button type="submit" className="auth-submit" disabled={loading || !username || !password}>
              {loading ? (
                <>
                  <Loader2 size={16} className="auth-spinner" />
                  Authenticating...
                </>
              ) : (
                'Access Dashboard'
              )}
            </button>
          </form>

          <div className="auth-footer">
            <p>New operator? <Link to="/signup">Request account access</Link></p>
            <div className="auth-badge">
              <ShieldCheck size={12} />
              <span>256-bit encrypted · JWT secured</span>
            </div>
            <p className="auth-version">SentinelIQ Platform v1.0 · Industrial AI Safety</p>
          </div>
        </div>
      </div>
    </div>
  );
}
