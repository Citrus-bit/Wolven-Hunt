import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 7001,
    proxy: {
      '/games': 'http://127.0.0.1:7002',
      '/models': 'http://127.0.0.1:7002',
      '/healthz': 'http://127.0.0.1:7002',
    },
  },
});
