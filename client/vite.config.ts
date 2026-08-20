import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Bind IPv4 explicitly — default "localhost" can be ::1-only on Windows,
    // which makes 127.0.0.1 / some browser tabs get ERR_CONNECTION_REFUSED.
    host: '127.0.0.1',
    port: 5173,
    // Fail instead of silently moving to 5174/5175 (broken tabs keep hitting dead proxies).
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:3001',
        changeOrigin: true,
      },
    },
  },
});
