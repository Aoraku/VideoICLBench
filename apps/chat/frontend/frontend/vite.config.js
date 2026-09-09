import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const devProxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000'
  // SECoder 通常将前端挂在 /chat 子路径；开发环境仍保持根路径便于本地调试。
  const appBase = mode === 'production' ? (env.VITE_BASE_PATH || '/chat/') : '/'

  return {
    base: appBase,
    plugins: [react()],
    server: {
      // WSL / 局域网：便于本机浏览器访问；端口以终端输出为准（5173 被占用时会自动换端口）
      host: true,
      proxy: {
        '/api': { target: devProxyTarget, changeOrigin: true },
        '/media': { target: devProxyTarget, changeOrigin: true },
        '/ws': { target: devProxyTarget, ws: true, changeOrigin: true },
      },
    },
  }
})
