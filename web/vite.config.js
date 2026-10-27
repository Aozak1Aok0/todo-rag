import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时把接口代理到本地 FastAPI（:8000），前端只写相对路径
export default defineConfig(({ command }) => ({
  // 构建产物挂在 FastAPI 的 /app 下；开发时仍从根路径访问
  base: command === 'build' ? '/app/' : '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/rag': 'http://127.0.0.1:8000',
      '/multi-agent': 'http://127.0.0.1:8000',
      '/chat': 'http://127.0.0.1:8000',
      '/stats': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
      '/docs': 'http://127.0.0.1:8000',
    },
  },
}))
