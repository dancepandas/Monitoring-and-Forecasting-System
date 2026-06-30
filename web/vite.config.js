import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cesium from 'vite-plugin-cesium'
import basicSsl from '@vitejs/plugin-basic-ssl'

export default defineConfig({
  plugins: [vue(), cesium(), basicSsl()],
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
