/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        avito: {
          green: '#00AAFF',
          dark: '#1a1a2e',
          sidebar: '#16213e',
          card: '#0f3460',
          accent: '#e94560',
        },
      },
    },
  },
  plugins: [],
}
