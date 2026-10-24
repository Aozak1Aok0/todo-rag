import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时把接口代理到本地 FastAPI（:8000），前端只写相对路径
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/rag': 'http://127.0.0.1:8000',
      '/chat': 'http://127.0.0.1:8000',
      '/stats': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
      '/docs': 'http://127.0.0.1:8000',
    },
  },
})