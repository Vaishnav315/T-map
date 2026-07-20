import React, { createContext, useContext, useState, useEffect } from 'react';
import { API_BASE, decodeToken } from './api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    // Check token expiry client-side before making a network call
    const payload = decodeToken(token);
    if (!payload) {
      // Token is expired or invalid
      logout();
      return;
    }

    // Verify with server
    fetch(`${API_BASE}/api/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error('Token rejected by server');
        return res.json();
      })
      .then((data) => setUser(data))
      .catch(() => logout())
      .finally(() => setLoading(false));
  }, [token]);

  const login = (newToken) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    // Decode user info from token immediately (no extra round-trip)
    const payload = decodeToken(newToken);
    if (payload) {
      setUser({ username: payload.sub, role: payload.role || 'viewer' });
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    setLoading(false);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
