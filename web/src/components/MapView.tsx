import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Heat, Hotspot, MapMeta, OpArea, Operator, Setup, SetupSpot } from '../types'
import { CAT_COLOR, Glyph, Icon } from './ui'

const S = 1000 // svg units across the full minimap square
type Box = [number, number, number, number] // x, y, width, height

export interface ReplayDraw {
  tokens: { x: number; y: number; side: string; label: string; name: string }[]
  trails: { side: string; points: string }[]
  casts: { x: number; y: number; cat: string; aim: [number, number] | null; fade: number }[]
  kills: { from: [number, number]; to: [number, number]; fade: number }[]
  plant: [number, number] | null
}

interface Props {
  map: string
  meta: MapMeta
  mode: 'utility' | 'operator' | 'setup' | 'replay'
  theme: 'light' | 'dark'
  hotspots?: Hotspot[]
  heat?: Heat | null
  showHeat?: boolean
  activeId?: string | null
  onHotspot?: (h: Hotspot) => void
  operator?: Operator | null
  opWindow?: number | null
  activeArea?: string | null
  onArea?: (a: OpArea) => void
  recurring?: Setup['recurring']
  setupSpots?: SetupSpot[]
  replay?: ReplayDraw | null
  focus?: { u: number; v: number } | null
  onResetFocus?: () => void
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    setW(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

/** Ease the viewBox to its target so selecting a spot moves the map instead of jumping. */
function useTween(target: Box): Box {
  const [box, setBox] = useState<Box>(target)
  const cur = useRef<Box>(target)
  const key = target.join(',')
  useEffect(() => {
    const from = cur.current
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce || from.every((v, i) => Math.abs(v - target[i]) < 0.5)) {
      cur.current = target
      setBox(target)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / 420)
      const e = 1 - Math.pow(2, -10 * p) // exponential ease-out
      const b = from.map((v, i) => v + (target[i] - v) * (p >= 1 ? 1 : e)) as Box
      cur.current = b
      setBox(b)
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return box
}

type Ramp = [number, number, number][]
export const HEAT_RAMP: Ramp = [[247, 205, 120], [233, 122, 62], [196, 52, 44], [112, 22, 48]] // low to high density
const SKY_RAMP: Ramp = [[160, 212, 240], [30, 155, 215], [16, 98, 150]]

function rampColor(ramp: Ramp, t: number): [number, number, number] {
  const f = Math.max(0, Math.min(1, t)) * (ramp.length - 1)
  const i = Math.min(ramp.length - 2, Math.floor(f))
  const a = ramp[i]
  const b = ramp[i + 1]
  return [a[0] + (b[0] - a[0]) * (f - i), a[1] + (b[1] - a[1]) * (f - i), a[2] + (b[2] - a[2]) * (f - i)]
}

/** Smoothed density grid to an image, square-root scaled so quieter areas stay visible. */
function useHeatImage(heat: Heat | null | undefined, ramp: Ramp, minAlpha: number) {
  return useMemo(() => {
    if (!heat || !heat.cells.length || typeof document === 'undefined') return null
    const n = heat.size || 128
    const cv = document.createElement('canvas')
    cv.width = n
    cv.height = n
    const ctx = cv.getContext('2d')!
    const img = ctx.createImageData(n, n)
    const max = Math.max(1e-6, heat.max)
    for (const [x, y, c] of heat.cells) {
      const k = Math.sqrt(Math.min(1, c / max))
      const [r, g, b] = rampColor(ramp, k)
      const i = (y * n + x) * 4
      img.data[i] = r
      img.data[i + 1] = g
      img.data[i + 2] = b
      img.data[i + 3] = Math.round(255 * Math.min(1, minAlpha + k * (1 - minAlpha)))
    }
    ctx.putImageData(img, 0, 0)
    return cv.toDataURL()
  }, [heat, ramp, minAlpha])
}

const short = (name: string) => name.replace('Attacker Spawn', 'Atk Spawn').replace('Defender Spawn', 'Def Spawn')

export function MapView(p: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const b = p.meta.bbox
  const base: Box = useMemo(() => [b[0] * S, b[1] * S, (b[2] - b[0]) * S, (b[3] - b[1]) * S], [b])
  const ratio = base[2] / base[3]

  const zoomed = !!p.focus && p.mode !== 'replay'
  const target: Box = useMemo(() => {
    if (!zoomed || !p.focus) return base
    const w = base[2] * 0.6
    const h = base[3] * 0.6
    const cx = Math.min(Math.max(p.focus.u * S, base[0] + w / 2), base[0] + base[2] - w / 2)
    const cy = Math.min(Math.max(p.focus.v * S, base[1] + h / 2), base[1] + base[3] - h / 2)
    return [cx - w / 2, cy - h / 2, w, h]
  }, [zoomed, p.focus, base])
  const view = useTween(target)
  const k = width > 0 ? view[2] / width : 1 // svg units per screen pixel
  const px = (n: number) => n * k

  const utilityHeat = useHeatImage(p.mode === 'utility' && p.showHeat ? p.heat : null, HEAT_RAMP, 0.18)
  const opHeatData = p.mode === 'operator' && p.operator ? (p.opWindow == null ? p.operator.heat : p.operator.windows_heat[p.opWindow]) : null
  const opHeat = useHeatImage(opHeatData, SKY_RAMP, 0.08)
  const heatUrl = utilityHeat ?? opHeat
  const uid = `m-${p.map}`

  const hs = p.hotspots ?? []
  const maxPct = Math.max(1, ...hs.map((h) => h.pct))
  const active = hs.find((h) => h.id === p.activeId)
  // Callout names give way to whatever is selected, and to each other: a name is dropped when
  // its box would overlap one already drawn (site names first, then the map's own order).
  const busy: { u: number; v: number }[] = []
  if (p.focus) busy.push(p.focus)
  if (p.mode === 'setup') busy.push(...(p.setupSpots ?? []))
  const callouts = useMemo(() => {
    const boxes: [number, number, number, number][] = []
    const out: { name: string; u: number; v: number; anchor: 'start' | 'middle' | 'end' }[] = []
    for (const c of p.meta.callouts) {
      if (/^[ABC] Site$/.test(c.name)) continue
      const label = short(c.name)
      const half = px(label.length * 3.3 + 4)
      const x = c.u * S
      const y = c.v * S
      if (busy.some((f) => Math.hypot((c.u - f.u) * S, (c.v - f.v) * S) < px(34))) continue
      // keep names near the left and right edges inside the drawing
      const anchor = x + half > base[0] + base[2] ? 'end' : x - half < base[0] ? 'start' : 'middle'
      const x0 = anchor === 'end' ? x - 2 * half : anchor === 'start' ? x : x - half
      const box: [number, number, number, number] = [x0, y - px(9), x0 + 2 * half, y + px(9)]
      if (boxes.some((o) => box[0] < o[2] && box[2] > o[0] && box[1] < o[3] && box[3] > o[1])) continue
      boxes.push(box)
      out.push({ name: label, u: c.u, v: c.v, anchor })
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.meta.callouts, k, base, p.focus, p.mode, p.setupSpots])

  // Markers arrive sorted by share. In a crowded spot only the strongest keeps its label, so
  // percentages never print on top of each other. The selected marker always keeps its own.
  const labelled = new Set<string>()
  const kept: Hotspot[] = []
  for (const h of active ? [active, ...hs.filter((x) => x.id !== active.id)] : hs) {
    if (active && h.id !== active.id) continue
    if (kept.every((o) => Math.hypot((o.u - h.u) * S, (o.v - h.v) * S) > px(40))) {
      kept.push(h)
      labelled.add(h.id)
    }
  }

  const areas = p.operator?.areas ?? []
  const areaValue = (a: OpArea) => (p.opWindow == null ? a.open_pct : a.window_share[p.opWindow] ?? 0)
  const maxArea = Math.max(1, ...areas.map(areaValue))

  return (
    <div className="map-fit">
      <div className="map-box" ref={ref} style={{ aspectRatio: String(ratio), width: `min(100cqw, calc(100cqh * ${ratio.toFixed(4)}))` }}>
        <svg className="map-svg" viewBox={view.join(' ')} role="img" aria-label={`${p.map} floor plan`}>
          <defs>
            <clipPath id={`${uid}-clip`}>
              <path d={p.meta.path} clipRule="evenodd" />
            </clipPath>
            <filter id={`${uid}-blur`} x="-10%" y="-10%" width="120%" height="120%">
              <feGaussianBlur stdDeviation="3.2" />
            </filter>
          </defs>

          <path className="floor" d={p.meta.path} fillRule="evenodd" />
          {heatUrl && (
            <g clipPath={`url(#${uid}-clip)`}>
              <image href={heatUrl} x="0" y="0" width={S} height={S} preserveAspectRatio="none" filter={`url(#${uid}-blur)`} />
            </g>
          )}
          <path className="walls" d={p.meta.path} fillRule="evenodd" vectorEffect="non-scaling-stroke" />

          {p.meta.sites.map((s) => (
            <g key={s.site} className="site-badge" aria-hidden="true">
              <rect x={s.u * S - px(11)} y={s.v * S - px(11)} width={px(22)} height={px(22)} rx={px(5)} />
              <text x={s.u * S} y={s.v * S + px(4.6)} fontSize={px(13)} textAnchor="middle">{s.site}</text>
            </g>
          ))}

          <g className="callouts" data-quiet={p.mode === 'replay'} aria-hidden="true">
            {callouts.map((c) => (
              <text key={c.name} x={c.u * S} y={c.v * S + px(4)} fontSize={px(11.5)} strokeWidth={px(3.2)} textAnchor={c.anchor}>
                {c.name}
              </text>
            ))}
          </g>

          {p.mode === 'utility' &&
            hs.map((h) => {
              const x = h.u * S
              const y = h.v * S
              const isActive = p.activeId === h.id
              const r = px(6.5 + 8.5 * Math.sqrt(h.pct / maxPct))
              const color = CAT_COLOR[h.category]
              const wall = h.placement === 'wall' && h.aim && h.aim_fit >= 0.75
              const tail = isActive && h.aim && (h.placement === 'thrown' || h.placement === 'ranged') && h.aim_fit >= 0.5
              return (
                <g
                  key={h.id}
                  className="marker"
                  data-active={isActive}
                  data-dim={!!active && !isActive}
                  onClick={() => p.onHotspot?.(h)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); p.onHotspot?.(h) } }}
                  role="button"
                  tabIndex={0}
                  aria-label={`${h.agent} ${h.ability_name}, ${h.callout}: ${h.k} of ${h.n} rounds`}
                >
                  {wall && (
                    <line x1={x} y1={y} x2={x + h.aim![0] * base[2] * 0.3} y2={y + h.aim![1] * base[2] * 0.3}
                          stroke={color} strokeWidth={px(isActive ? 3 : 2)} strokeLinecap="round" opacity={isActive ? 0.9 : 0.4} />
                  )}
                  {tail && (
                    <line x1={x} y1={y} x2={x + h.aim![0] * px(54)} y2={y + h.aim![1] * px(54)}
                          stroke={color} strokeWidth={px(2.2)} strokeLinecap="round" strokeDasharray={`${px(1)} ${px(5)}`} />
                  )}
                  <circle className="halo" cx={x} cy={y} r={r * 1.75} fill={color} />
                  {isActive && <circle className="ring" cx={x} cy={y} r={r * 1.75 + px(4)} strokeWidth={px(1.6)} />}
                  <Glyph cat={h.category} x={x} y={y} r={r * 0.6} />
                  {labelled.has(h.id) && (
                    <text className="marker-label" x={x + r + px(5)} y={y + px(4.4)} fontSize={px(12.5)} strokeWidth={px(3.4)}>
                      {h.p}%
                    </text>
                  )}
                  <title>{`${h.agent} ${h.ability_name}, ${h.callout}: ${h.k} of ${h.n} rounds`}</title>
                </g>
              )
            })}

          {p.mode === 'operator' && p.operator && (
            <g>
              {p.operator.kills.lines.map((l, i) => (
                <g key={i} className={l.first ? 'sight sight-open' : 'sight'}>
                  <line x1={l.from[0] * S} y1={l.from[1] * S} x2={l.to[0] * S} y2={l.to[1] * S} strokeWidth={px(l.first ? 1.8 : 1.1)} />
                  <circle cx={l.to[0] * S} cy={l.to[1] * S} r={px(l.first ? 3 : 2.2)} />
                </g>
              ))}
              {areas.map((a, i) => {
                const val = areaValue(a)
                const r = px(7 + 10 * Math.sqrt(val / maxArea))
                const isActive = p.activeArea === a.callout
                return (
                  <g key={a.callout} className="marker" data-active={isActive} data-dim={!!p.activeArea && !isActive}
                     style={{ opacity: val > 0 || isActive ? undefined : 0.25 }}
                     onClick={() => p.onArea?.(a)}
                     onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); p.onArea?.(a) } }}
                     role="button" tabIndex={0} aria-label={`Operator at ${a.callout}`}>
                    <circle className="halo" cx={a.u * S} cy={a.v * S} r={r * 1.7} fill="var(--sky-fill)" />
                    {isActive && <circle className="ring" cx={a.u * S} cy={a.v * S} r={r * 1.7 + px(4)} strokeWidth={px(1.6)} />}
                    <circle cx={a.u * S} cy={a.v * S} r={r * 0.55} fill="var(--sky-fill)" stroke="var(--floor)" strokeWidth={px(2)} />
                    {(i < 4 || isActive) && (
                      <text className="marker-label" x={a.u * S + r + px(5)} y={a.v * S + px(4.4)} fontSize={px(12.5)} strokeWidth={px(3.4)}>
                        {p.opWindow == null ? `${a.open_k}/${a.open_n}` : `${Math.round(val)}%`}
                      </text>
                    )}
                    <title>{`${a.callout} (${a.style})`}</title>
                  </g>
                )
              })}
            </g>
          )}

          {p.mode === 'setup' && (
            <g>
              {(p.recurring ?? []).map((s) => {
                const on = (p.setupSpots ?? []).some((x) => x.id === s.id)
                return (
                  <g key={s.id} className="marker" data-dim={!on}>
                    {on && <circle className="halo" cx={s.u * S} cy={s.v * S} r={px(22)} fill="var(--c-trap)" />}
                    <Glyph cat="trap" x={s.u * S} y={s.v * S} r={px(on ? 7 : 5)} color={on ? undefined : 'var(--ink-3)'} />
                    {on && (
                      <text className="marker-label" x={s.u * S + px(13)} y={s.v * S + px(4.4)} fontSize={px(12.5)} strokeWidth={px(3.4)}>
                        {s.ability_name}
                      </text>
                    )}
                    <title>{`${s.agent} ${s.ability_name}, ${s.callout}`}</title>
                  </g>
                )
              })}
            </g>
          )}

          {p.mode === 'replay' && p.replay && (
            <g>
              {p.replay.trails.map((t, i) => (
                <polyline key={i} className="trail" data-side={t.side} points={t.points} strokeWidth={px(2)} />
              ))}
              {p.replay.kills.map((kl, i) => (
                <g key={i} className="kill" opacity={kl.fade}>
                  <line x1={kl.from[0] * S} y1={kl.from[1] * S} x2={kl.to[0] * S} y2={kl.to[1] * S} strokeWidth={px(1.6)} />
                  <path d={`M${kl.to[0] * S - px(5)} ${kl.to[1] * S - px(5)}l${px(10)} ${px(10)}m0 ${-px(10)}l${-px(10)} ${px(10)}`} strokeWidth={px(2.6)} />
                </g>
              ))}
              {p.replay.casts.map((c, i) => (
                <g key={i} opacity={c.fade}>
                  {c.aim && <line x1={c.x * S} y1={c.y * S} x2={c.x * S + c.aim[0] * px(34)} y2={c.y * S + c.aim[1] * px(34)} stroke={CAT_COLOR[c.cat]} strokeWidth={px(1.8)} strokeLinecap="round" />}
                  <Glyph cat={c.cat} x={c.x * S} y={c.y * S} r={px(5.5)} />
                </g>
              ))}
              {p.replay.plant && (
                <g className="spike">
                  <circle cx={p.replay.plant[0] * S} cy={p.replay.plant[1] * S} r={px(12)} strokeWidth={px(2.4)} />
                  <circle cx={p.replay.plant[0] * S} cy={p.replay.plant[1] * S} r={px(4)} className="spike-core" />
                </g>
              )}
              {p.replay.tokens.map((d, i) => (
                <g key={i} className="token" data-side={d.side}>
                  <circle cx={d.x * S} cy={d.y * S} r={px(11)} strokeWidth={px(2)} />
                  <text className="token-code" x={d.x * S} y={d.y * S + px(3.6)} fontSize={px(10)} textAnchor="middle">{d.label}</text>
                  <text className="token-name" x={d.x * S} y={d.y * S + px(24)} fontSize={px(11)} strokeWidth={px(3)} textAnchor="middle">{d.name}</text>
                </g>
              ))}
            </g>
          )}
        </svg>
        {zoomed && (
          <button type="button" className="map-reset" onClick={p.onResetFocus}>
            <Icon name="reset" size={14} /> Whole map
          </button>
        )}
      </div>
    </div>
  )
}
