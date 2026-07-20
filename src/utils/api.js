/**
 * SentinelIQ AI Safety Platform
 * Utility for constructing API URLs.
 * - In development: uses Vite proxy (backendUrl = '')
 * - In production build: uses VITE_API_URL env var
 */

export const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Authenticated fetch wrapper.
 * Automatically attaches JWT Authorization header.
 */
export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('token');
  const headers = {
    ...(options.headers || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  return fetch(`${API_BASE}${path}`, { ...options, headers });
}

/**
 * Decode a JWT payload (without verifying signature — client-side only).
 * Returns null if the token is invalid or expired.
 */
export function decodeToken(token) {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && payload.exp < now) return null; // expired
    return payload;
  } catch {
    return null;
  }
}
