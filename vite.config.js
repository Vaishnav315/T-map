import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  // In development, proxy to local backend.
  // In production (npm run build), VITE_API_URL is embedded at build time.
  const backendTarget = env.VITE_API_URL || 'http://localhost:5001';

  return {
    plugins: [react()],

    // App title
    define: {
      'import.meta.env.VITE_APP_NAME': JSON.stringify('SentinelIQ AI Safety Platform'),
    },

    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          timeout: 10000,
        },
        '/video_feed': {
          target: backendTarget,
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,  // streaming — no timeout
        },
        '/evidence': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },

    build: {
      outDir: 'dist',
      sourcemap: false,
      rollupOptions: {
        output: {
          // Native chunking enabled
        },
      },
    },
  };
});
