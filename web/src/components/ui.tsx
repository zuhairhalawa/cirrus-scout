import type { ReactNode } from 'react'
import type { Strength } from '../types'

export const CAT_COLOR: Record<string, string> = {
  trap: 'var(--c-trap)', sentinel: 'var(--c-sentinel)', recon: 'var(--c-recon)', smoke: 'var(--c-smoke)',
  stall: 'var(--c-stall)', flash: 'var(--c-flash)', damage: 'var(--c-damage)', ult: 'var(--c-ult)', other: 'var(--ink-3)',
}
export const CAT_LABEL: Record<string, string> = {
  trap: 'Traps and cams', sentinel: 'Sentinel area denial', recon: 'Recon', smoke: 'Smokes and walls',
  stall: 'Stall and slow', flash: 'Flashes', damage: 'Damage', ult: 'Ultimates', other: 'Other',
}
export const CAT_ORDER = ['trap', 'sentinel', 'recon', 'smoke', 'stall', 'flash', 'damage', 'ult']

/** One shape per utility category, so markers stay readable without relying on colour alone. */
export function Glyph({ cat, x, y, r, color, ring = 'var(--floor)' }: { cat: string; x: number; y: number; r: number; color?: string; ring?: string }) {
  const c = color ?? CAT_COLOR[cat] ?? 'var(--ink-3)'
  const common = { fill: c, stroke: ring, strokeWidth: r * 0.28 }
  switch (cat) {
    case 'trap':
      return <rect x={x - r} y={y - r} width={r * 2} height={r * 2} rx={r * 0.18} {...common} />
    case 'sentinel':
      return <rect x={x - r * 0.9} y={y - r * 0.9} width={r * 1.8} height={r * 1.8} transform={`rotate(45 ${x} ${y})`} {...common} />
    case 'stall':
      return <path d={`M${x} ${y - r * 1.15}L${x + r * 1.1} ${y + r * 0.85}L${x - r * 1.1} ${y + r * 0.85}Z`} {...common} />
    case 'flash': {
      const p: string[] = []
      for (let i = 0; i < 8; i++) {
        const a = (Math.PI / 4) * i - Math.PI / 2
        const rr = i % 2 === 0 ? r * 1.3 : r * 0.55
        p.push(`${x + Math.cos(a) * rr},${y + Math.sin(a) * rr}`)
      }
      return <polygon points={p.join(' ')} {...common} />
    }
    case 'damage':
      return (
        <g>
          <path d={`M${x - r} ${y - r}L${x + r} ${y + r}M${x + r} ${y - r}L${x - r} ${y + r}`} stroke={ring} strokeWidth={r * 0.95} strokeLinecap="round" />
          <path d={`M${x - r} ${y - r}L${x + r} ${y + r}M${x + r} ${y - r}L${x - r} ${y + r}`} stroke={c} strokeWidth={r * 0.5} strokeLinecap="round" />
        </g>
      )
    case 'ult':
      return <path d={`M${x} ${y - r * 1.2}L${x + r * 1.05} ${y}L${x} ${y + r * 1.2}L${x - r * 1.05} ${y}Z`} {...common} />
    default:
      return <circle cx={x} cy={y} r={r} {...common} />
  }
}

export function GlyphIcon({ cat, size = 16 }: { cat: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className="glyph-icon">
      <Glyph cat={cat} x={8} y={8} r={4.6} ring="var(--panel)" />
    </svg>
  )
}

export function Seg<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { id: T; label: string; title?: string }[]; onChange: (v: T) => void
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" aria-pressed={value === o.id} title={o.title} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

const STRENGTH_LABEL: Record<Strength, string> = { strong: 'Strong evidence', moderate: 'Moderate evidence', thin: 'Thin evidence' }
const STRENGTH_HELP: Record<Strength, string> = {
  strong: '15 or more rounds, and at least 40% of them even on a cautious estimate.',
  moderate: '8 or more rounds, and at least 20% of them even on a cautious estimate.',
  thin: 'Too few rounds, or too small a share, to rely on. Treat it as a lead to check.',
}

export function StrengthChip({ s }: { s: Strength }) {
  return (
    <span className="strength" data-s={s} title={STRENGTH_HELP[s]}>
      <i aria-hidden="true" />
      {STRENGTH_LABEL[s]}
    </span>
  )
}

export function ShareBar({ pct, tone = 'ink' }: { pct: number; tone?: 'ink' | 'sky' }) {
  return (
    <span className="share-bar" data-tone={tone} aria-hidden="true">
      <span style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </span>
  )
}

export function Icon({ name, size = 16 }: { name: 'play' | 'pause' | 'sun' | 'moon' | 'print' | 'help' | 'reset' | 'close'; size?: number }) {
  const p: Record<string, ReactNode> = {
    play: <path d="M5 3.5v9l7.5-4.5z" fill="currentColor" stroke="none" />,
    pause: <path d="M4.5 3.5h2.5v9H4.5zM9 3.5h2.5v9H9z" fill="currentColor" stroke="none" />,
    sun: <><circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.7M8 12.8v1.7M1.5 8h1.7M12.8 8h1.7M3.4 3.4l1.2 1.2M11.4 11.4l1.2 1.2M12.6 3.4l-1.2 1.2M4.6 11.4l-1.2 1.2" /></>,
    moon: <path d="M13 9.6A5.5 5.5 0 0 1 6.4 3 5.5 5.5 0 1 0 13 9.6z" />,
    print: <><path d="M4.5 6V2.5h7V6M4.5 11.5h-2v-5h11v5h-2" /><path d="M4.5 9.5h7v4h-7z" /></>,
    help: <><circle cx="8" cy="8" r="6" /><path d="M6.3 6.3a1.8 1.8 0 1 1 2.6 1.6c-.6.3-.9.7-.9 1.3M8 11.4v.2" /></>,
    reset: <><path d="M3 8a5 5 0 1 0 1.6-3.7" /><path d="M3 3v2.6h2.6" /></>,
    close: <path d="M4 4l8 8M12 4l-8 8" />,
  }
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {p[name]}
    </svg>
  )
}

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
export const clock = (t: number) => {
  const s = Math.max(0, Math.round(t))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
