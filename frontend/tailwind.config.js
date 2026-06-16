/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      keyframes: {
        fadeInScale: {
          '0%': { opacity: '0', transform: 'scale(0.95) translateY(8px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        flashHighlight: {
          '0%':   { backgroundColor: 'transparent' },
          '15%':  { backgroundColor: 'rgb(254 240 138)' },
          '60%':  { backgroundColor: 'rgb(187 247 208)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
      animation: {
        'fade-in-scale':   'fadeInScale 0.2s ease-out forwards',
        'flash-highlight': 'flashHighlight 1.8s ease-out forwards',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
