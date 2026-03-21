/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          bg: '#0f0f13',
          surface: '#1a1a24',
          accent: '#e5a00d',
          text: '#e8e8e8',
        },
        success: '#4caf50',
        error: '#e53935',
        info: '#42a5f5',
      },
    },
  },
  plugins: [],
}
