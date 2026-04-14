/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bbva: {
          dark: '#003B5C',
          primary: '#0066A1',
          light: '#1A8FD1',
        },
        helpyy: {
          primary: '#00a870',
          dark: '#008c5a',
          teal: '#00897b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
