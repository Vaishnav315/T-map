import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ShieldCheck, Eye, EyeOff, Loader2, AlertCircle, Key } from 'lucide-react';
import { apiFetch } from '../utils/api';

export default function Signup() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const navigate = useNavigate();

  const validatePassword = (pass) => {
    if (pass.length < 8) return "Password must be at least 8 characters long.";
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    const passError = validatePassword(password);
    if (passError) {
      setError(passError);
      return;
    }

    setLoading(true);

    try {
      const res = await apiFetch('/api/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      });

      const data = await res.json();

      if (res.ok) {
        setSuccess(true);
        setTimeout(() => navigate('/login'), 2500);
      } else {
        setError(data.detail || 'Registration failed');
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

      {/* Right Side: Signup Form */}
      <div className="auth-right">
        <div className="auth-form-container">
          <div className="auth-form-header">
            <h3>Operator Registration</h3>
            <p>Create your account to access the SentinelIQ platform.</p>
          </div>

          {success ? (
            <div className="auth-success-box">
              <ShieldCheck size={32} color="#10b981" />
              <h4>Account Created Successfully</h4>
              <p>Your operator account has been registered. Redirecting to login...</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="auth-form">
              <div className="auth-input-group">
                <label>Username</label>
                <input
                  type="text"
                  className="auth-input"
                  placeholder="e.g. operator_01"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  disabled={loading}
                />
              </div>

              <div className="auth-input-group">
                <label>Email</label>
                <input
                  type="email"
                  className="auth-input"
                  placeholder="operator@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
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
                    placeholder="Min. 8 characters"
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
                <div className="auth-password-hint">
                  <Key size={12} />
                  Must be at least 8 characters long
                </div>
              </div>

              {error && (
                <div className="auth-error">
                  <AlertCircle size={14} />
                  <span>{error}</span>
                </div>
              )}

              <button type="submit" className="auth-submit" disabled={loading || !username || !email || !password}>
                {loading ? (
                  <>
                    <Loader2 size={16} className="auth-spinner" />
                    Registering...
                  </>
                ) : (
                  'Create Account'
                )}
              </button>
            </form>
          )}

          <div className="auth-footer">
            <p>Already an operator? <Link to="/login">Return to login</Link></p>
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
