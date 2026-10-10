import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // The recorded API responses live in the backend's docs/api_examples/ (one copy only).
    fs: { allow: ['..'] },
  },
  // The bundle carries the recorded mainnet responses (~125 kB) so the demo runs offline.
  build: { chunkSizeWarningLimit: 900 },
})
