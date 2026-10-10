import type { Config } from 'tailwindcss'

/**
 * Apple-minimal design system.
 * Only two font weights exist in this theme: Regular (400) and Semibold (600).
 * Only the colour tokens below may be used — nothing else is in the palette.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: '#000000',        // page background
        surface: '#1C1C1E',    // drawers, inputs, solid panels
        surface2: '#2C2C2E',   // inert bar track
        chalk: '#F5F5F7',      // primary text
        neutral1: '#8E8E93',   // secondary text + layer 1 nodes
        accent: '#0071E3',     // primary action, layer 2 + 4 nodes
        risk: '#FF3B30',       // layer 5, exit verdict
        safe: '#34C759',       // stay verdict
        warn: '#FF9F0A',       // layer 3 oracle
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'SF Pro Text',
          'SF Pro Display',
          'system-ui',
          'Segoe UI',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
      },
      fontSize: {
        // Deliberately sparse: no timid mid-sizes.
        caption: ['13px', { lineHeight: '18px', letterSpacing: '0' }],
        body: ['17px', { lineHeight: '26px', letterSpacing: '0' }],
        graph: ['20px', { lineHeight: '26px', letterSpacing: '-0.01em' }],
        panel: ['28px', { lineHeight: '34px', letterSpacing: '-0.02em' }],
        field: ['24px', { lineHeight: '32px', letterSpacing: '-0.01em' }],
        sub: ['32px', { lineHeight: '38px', letterSpacing: '-0.02em' }],
        title: ['40px', { lineHeight: '46px', letterSpacing: '-0.02em' }],
        figure: ['72px', { lineHeight: '76px', letterSpacing: '-0.03em' }],
        headline: ['64px', { lineHeight: '68px', letterSpacing: '-0.03em' }],
        display: ['80px', { lineHeight: '84px', letterSpacing: '-0.035em' }],
        verdict: ['96px', { lineHeight: '96px', letterSpacing: '-0.04em' }],
        lead: ['24px', { lineHeight: '34px', letterSpacing: '-0.01em' }],
        // The answer to the only question that matters at 3 a.m.
        giant: ['clamp(104px, 19vw, 248px)', { lineHeight: '0.88', letterSpacing: '-0.055em' }],
      },
      fontWeight: {
        normal: '400',
        semibold: '600',
      },
      spacing: {
        // 8pt grid extensions
        18: '4.5rem',
        30: '7.5rem',
        34: '8.5rem',
        42: '10.5rem',
      },
      borderRadius: {
        // Nothing in the system exceeds 12px, except circles (nodes).
        none: '0px',
        sm: '4px',
        md: '8px',
        lg: '10px',
        xl: '12px',
      },
      maxWidth: {
        stage: '1320px',
      },
      keyframes: {
        'progress-slide': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(250%)' },
        },
        // Incident ring — pure CSS keyframes, no animation library.
        'pulse-ring': {
          '0%': { transform: 'scale(0.72)', opacity: '0.9' },
          '70%': { transform: 'scale(2.1)', opacity: '0' },
          '100%': { transform: 'scale(2.1)', opacity: '0' },
        },
        'pulse-core': {
          '0%, 100%': { opacity: '0.95' },
          '50%': { opacity: '0.45' },
        },
      },
      animation: {
        progress: 'progress-slide 1400ms cubic-bezier(0.4, 0, 0.2, 1) infinite',
        'pulse-ring': 'pulse-ring 1800ms cubic-bezier(0.22, 0.61, 0.36, 1) infinite',
        'pulse-core': 'pulse-core 1800ms ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
