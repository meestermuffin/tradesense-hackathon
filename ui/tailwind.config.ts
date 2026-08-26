import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: '#020617',
        surface: '#0f172a',
        'surface-2': '#1e293b',
        'surface-3': '#334155',
        border: '#1e293b',
        'border-2': '#334155',
        buy: '#34d399',
        'buy-dim': '#064e3b',
        sell: '#f87171',
        'sell-dim': '#7f1d1d',
        hold: '#94a3b8',
        accent: '#3b82f6',
        'accent-dim': '#1e3a8a',
        warning: '#fbbf24',
        'warning-dim': '#78350f',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      keyframes: {
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
      },
      animation: {
        marquee: 'marquee 40s linear infinite',
      },
    },
  },
  plugins: [],
}

export default config
