import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // vitest — happy-dom 환경에서 React 컴포넌트 테스트 (jsdom 27 ESM 충돌 우회)
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./tests/vitest.setup.js'],
    include: ['tests/**/*.test.{js,jsx}'],
  },
  // .wasm 파일을 Vite asset으로 취급 → ?url 임포트 + fetch() 정상 동작
  assetsInclude: ['**/*.wasm'],
  server: {
    port: 5173,
    // 클라우드플레어 퀵 터널의 임시 도메인(*.trycloudflare.com) 통과 허용
    allowedHosts: ['.trycloudflare.com'],
    // react-router-dom BrowserRouter — 404를 index.html로 폴백
    historyApiFallback: true,
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