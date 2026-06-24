/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  // 다크 모드: <div class="dark"> 토글 방식
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        // Noto Sans KR 우선 적용
        sans: ['Noto Sans KR', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        // 기존 채팅 애니메이션
        fadeInScale: {
          '0%':   { opacity: '0', transform: 'scale(0.95) translateY(8px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        flashHighlight: {
          '0%':   { backgroundColor: 'transparent' },
          '15%':  { backgroundColor: 'rgb(254 240 138)' },
          '60%':  { backgroundColor: 'rgb(187 247 208)' },
          '100%': { backgroundColor: 'transparent' },
        },
        // 와이어프레임 날짜 하이라이트 펄스
        hlPulse: {
          '0%':   { backgroundColor: 'rgba(250,204,21,0)' },
          '22%':  { backgroundColor: 'rgba(250,204,21,.85)' },
          '100%': { backgroundColor: 'rgba(250,204,21,.32)' },
        },
        // 자동화 배너 슬라이드 업
        bannerUp: {
          from: { transform: 'translate(-50%, 18px)', opacity: '0' },
          to:   { transform: 'translate(-50%, 0)',    opacity: '1' },
        },
        // 메시지 페이드인
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in-scale':   'fadeInScale 0.2s ease-out forwards',
        'flash-highlight': 'flashHighlight 1.8s ease-out forwards',
        'hl-pulse':        'hlPulse 1.7s cubic-bezier(.4,0,.2,1) forwards',
        'banner-up':       'bannerUp .35s ease forwards',
        'fade-in':         'fadeIn .3s ease forwards',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
