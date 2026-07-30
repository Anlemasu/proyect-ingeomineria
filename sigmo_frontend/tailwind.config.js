/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#1E40AF',
          accent: '#0EA5E9',
          sidebar: '#1E293B',
          'sidebar-active': '#3B82F6',
        },
        gold: {
          50: '#FFFBEA',
          100: '#FFF3C4',
          200: '#FCE588',
          300: '#FAD54B',
          400: '#FCC419',
          500: '#FBB903',
          600: '#D69E00',
          700: '#A67C00',
          800: '#7A5B00',
          900: '#4D3900',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

