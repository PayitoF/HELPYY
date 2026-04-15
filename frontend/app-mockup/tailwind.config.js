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
          primary: '#0727b5',
          dark: '#0b1650',
          teal: '#1a3fd1',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
