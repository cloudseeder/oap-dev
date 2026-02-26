import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: '../oap_agent/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/v1/agent': 'http://localhost:8303',
    },
  },
})
