import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:15002',
        changeOrigin: true,
        timeout: 30000
      }
    },
    headers: {
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-cache'
    }
  }
})
