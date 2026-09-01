/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        abyss: '#07070a',
        panel: '#0f0f15',
        panelSoft: '#111827',
        borderGlow: '#1d1d26',
        cyan: '#00f0ff',
        lime: '#a6ff00',
        amber: '#ffaa00',
        crimson: '#ff3b30',
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(0,240,255,0.18), 0 0 30px rgba(0,240,255,0.18)',
      },
      backgroundImage: {
        mesh: 'radial-gradient(circle at top left, rgba(0,240,255,.16), transparent 30%), radial-gradient(circle at bottom right, rgba(166,255,0,.10), transparent 35%)',
      },
    },
  },
  plugins: [],
};
