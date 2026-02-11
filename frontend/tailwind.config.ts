import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: 'class',
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          base: 'rgb(var(--color-bg-base) / <alpha-value>)',
          surface: 'rgb(var(--color-bg-surface) / <alpha-value>)',
          elevated: 'rgb(var(--color-bg-elevated) / <alpha-value>)',
          border: 'rgb(var(--color-border) / <alpha-value>)',
        },
        accent: {
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
        },
        'text-primary': 'rgb(var(--color-text-primary) / <alpha-value>)',
        'text-secondary': 'rgb(var(--color-text-secondary) / <alpha-value>)',
        'text-tertiary': 'rgb(var(--color-text-tertiary) / <alpha-value>)',
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: '65ch',
            color: 'rgb(var(--color-text-primary))',
            a: {
              color: '#2dd4bf',
              '&:hover': {
                color: '#14b8a6',
              },
            },
            strong: {
              color: 'rgb(var(--color-text-primary))',
            },
            h1: { color: 'rgb(var(--color-text-primary))' },
            h2: { color: 'rgb(var(--color-text-primary))' },
            h3: { color: 'rgb(var(--color-text-primary))' },
            h4: { color: 'rgb(var(--color-text-primary))' },
            blockquote: {
              color: 'rgb(var(--color-text-secondary))',
              borderLeftColor: 'rgb(var(--color-border))',
            },
            code: {
              color: 'rgb(var(--color-text-primary))',
              backgroundColor: 'rgb(var(--color-bg-elevated))',
            },
            'code::before': { content: 'none' },
            'code::after': { content: 'none' },
            hr: { borderColor: 'rgb(var(--color-border))' },
            'ol > li::marker': { color: 'rgb(var(--color-text-secondary))' },
            'ul > li::marker': { color: 'rgb(var(--color-text-secondary))' },
            thead: {
              borderBottomColor: 'rgb(var(--color-border))',
            },
            'tbody tr': {
              borderBottomColor: 'rgb(var(--color-border))',
            },
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
export default config;
