/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans   : ['var(--font-body)'],
        display: ['var(--font-display)'],
        mono   : ['var(--font-mono)'],
      },
      colors: {
        olive: {
          50 : '#f4f6e8',
          100: '#e6ecd0',
          200: '#cddba0',
          300: '#afc670',
          400: '#8fae45',
          500: '#6b7c3a',
          600: '#556030',
          700: '#404828',
          800: '#2e3320',
          900: '#1e2218',
        },
        sand: {
          50 : '#fdf9ef',
          100: '#f8f0dc',
          200: '#f0ddb4',
          300: '#e5c480',
          400: '#d4a855',
          500: '#b89650',
          600: '#967840',
          700: '#7a5c30',
          800: '#5a4222',
          900: '#3c2c16',
        },
      },
      boxShadow: {
        'card'     : '0 1px 3px rgba(28,26,14,0.07)',
        'card-md'  : '0 4px 16px rgba(28,26,14,0.09)',
        'card-lg'  : '0 12px 40px rgba(28,26,14,0.12)',
        'card-glow': '0 0 0 1px var(--accent), 0 4px 20px rgba(97,112,56,0.28)',
        'dark-card'   : '0 1px 3px rgba(0,0,0,0.32)',
        'dark-card-md': '0 4px 16px rgba(0,0,0,0.42)',
        'dark-card-lg': '0 12px 40px rgba(0,0,0,0.58)',
        'olive'    : '0 4px 14px rgba(97,112,56,0.35)',
        'sand'     : '0 4px 14px rgba(184,150,80,0.35)',
      },
      borderRadius: {
        'card': '14px',
        'btn' : '8px',
        'pill': '999px',
      },
      animation: {
        'fade-in'    : 'fadeIn 0.35s ease forwards',
        'slide-up'   : 'slideUp 0.35s ease forwards',
        'slide-in-left': 'slideInLeft 0.3s ease forwards',
        'pulse-slow' : 'pulse 3s ease-in-out infinite',
        'float'      : 'float 3s ease-in-out infinite',
        'spin-slow'  : 'spin 8s linear infinite',
      },
      keyframes: {
        fadeIn     : { from: { opacity: 0 },                        to: { opacity: 1 } },
        slideUp    : { from: { opacity: 0, transform: 'translateY(14px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        slideInLeft: { from: { opacity: 0, transform: 'translateX(-12px)' }, to: { opacity: 1, transform: 'translateX(0)' } },
        float      : {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%'     : { transform: 'translateY(-6px)' },
        },
      },
      screens: {
        'xs': '400px',
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      transitionDuration: {
        '250': '250ms',
      },
    },
  },
  plugins: [],
}
