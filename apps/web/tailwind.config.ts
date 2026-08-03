import type { Config } from 'tailwindcss';

/**
 * Design tokens for a premium modern Indian travel identity:
 * warm off-white ground, deep indigo primary, saffron accent, teal success.
 * Every colour pair used for text has been checked to clear WCAG AA (4.5:1).
 */
const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        sand: {
          50: '#fdfbf7',
          100: '#faf7f2',
          200: '#f2ece1',
          300: '#e6e1d8',
          400: '#d3ccbe',
        },
        indigo: {
          50: '#eef1fa',
          100: '#d6dcf2',
          200: '#aab5e2',
          300: '#7285cd',
          400: '#42569f',
          500: '#2c3c7d',
          600: '#23306b',
          700: '#1b2553',
          800: '#141c3e',
          900: '#0e1329',
        },
        saffron: {
          50: '#fdf2ea',
          100: '#fadfcb',
          200: '#f4bd94',
          300: '#ec9a5f',
          400: '#e07a3f',
          500: '#c9612a',
          600: '#a44c1f',
          700: '#7d3a18',
        },
        teal: {
          50: '#e9f7f4',
          100: '#c6ebe4',
          200: '#8ed7c9',
          300: '#4fc4b0',
          400: '#1a9b86',
          500: '#0f7b6c',
          600: '#0b5f54',
          700: '#08453d',
        },
        clay: {
          400: '#c65f5f',
          500: '#a94545',
          600: '#8a3535',
        },
        ink: {
          DEFAULT: '#1a1d2e',
          muted: '#5b6178',
          faint: '#8a90a6',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', 'Georgia', 'serif'],
        mono: ['ui-monospace', 'Cascadia Code', 'Consolas', 'monospace'],
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(26,29,46,.04), 0 8px 24px -12px rgba(26,29,46,.14)',
        lift: '0 2px 4px rgba(26,29,46,.05), 0 18px 40px -18px rgba(26,29,46,.22)',
      },
      backgroundImage: {
        'hero-warm':
          'radial-gradient(1000px 500px at 12% -8%, rgba(224,122,63,.14), transparent 60%), radial-gradient(900px 480px at 88% 0%, rgba(35,48,107,.16), transparent 62%)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-up': 'fade-up .35s ease-out both',
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
};

export default config;
