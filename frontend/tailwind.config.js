/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        graph: {
          bg:      "#0f1117",
          panel:   "#1a1d27",
          border:  "#2a2d3a",
          accent:  "#6366f1",
          success: "#22c55e",
          warning: "#f59e0b",
          danger:  "#ef4444",
        }
      }
    },
  },
  plugins: [],
}