/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f5f3ff', 100: '#ede9fe', 200: '#ddd6fe', 300: '#c4b5fd', 400: '#a78bfa',
          500: '#8b5cf6', 600: '#6d28d9', 700: '#5b21b6', 800: '#4c1d95', 900: '#2e1065',
        },
        ink: { 900: '#0b0b12', 800: '#1f2937', 600: '#4b5563', 500: '#6b7280', 400: '#9ca3af' },
      },
      fontFamily: { sans: ['Manrope', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'] },
      boxShadow: { card: '0 1px 2px rgba(17,24,39,.04), 0 4px 16px rgba(91,33,182,.05)' },
    },
  },
  plugins: [],
};
