import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // .wasm 파일을 Vite asset으로 취급 → ?url 임포트 + fetch() 정상 동작
  assetsInclude: ['**/*.wasm'],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // 업로드 파일 미리보기 / 아티팩트 다운로드
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
