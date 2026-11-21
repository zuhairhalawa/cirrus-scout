import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `base: './'` lets the same build run from the local server or a static host subpath.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/maps': 'http://127.0.0.1:8765',
    },
  },
  build: { chunkSizeWarningLimit: 900 },
})
