/** The palette, for canvas drawing and inline styles. Mirrors tailwind.config.ts. */
export const C = {
  ink: '#000000',
  surface: '#1C1C1E',
  surface2: '#2C2C2E',
  chalk: '#F5F5F7',
  neutral: '#8E8E93',
  accent: '#0071E3',
  risk: '#FF3B30',
  safe: '#34C759',
  warn: '#FF9F0A',
} as const

export const verdictColor = (verdict: string | null | undefined) =>
  verdict === 'EXIT' ? C.risk : verdict === 'STAY' ? C.safe : C.neutral
