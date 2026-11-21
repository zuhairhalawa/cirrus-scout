import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MapMeta, Replay } from '../types'
import { MapView, type ReplayDraw } from './MapView'
import { Icon, Seg, clock } from './ui'

const S = 1000
const TRAIL_SECONDS = 7
type Track = { t: number[]; u: number[]; v: number[] }

/** Round clock shared between the map and the event feed without re-rendering the whole app. */
function createClock() {
  let t = 0
  const subs = new Set<() => void>()
  return {
    get: () => t,
    set: (v: number) => { t = v; subs.forEach((f) => f()) },
    subscribe: (f: () => void) => { subs.add(f); return () => { subs.delete(f) } },
  }
}
export const replayClock = createClock()

const agentCode = (agent: string) => agent.replace(/[^a-zA-Z]/g, '').slice(0, 2).toUpperCase()

function buildTracks(r: Replay) {
  const tracks: Track[] = r.players.map(() => ({ t: [], u: [], v: [] }))
  for (const fr of r.frames) {
    const t = fr[0] as number
    for (let i = 1; i < fr.length; i++) {
      const [pi, u, v] = fr[i] as [number, number, number]
      const tr = tracks[pi]
      if (!tr) continue
      tr.t.push(t); tr.u.push(u); tr.v.push(v)
    }
  }
  const deathAt = new Map<number, number>()
  for (const k of r.kills) if (k.victim !== null && !deathAt.has(k.victim)) deathAt.set(k.victim, k.t)
  const lastFrame = r.frames.length ? (r.frames[r.frames.length - 1][0] as number) : 0
  return { tracks, deathAt, end: Math.max(r.duration || 0, lastFrame) }
}

function sample(tr: Track, t: number): [number, number] | null {
  const n = tr.t.length
  if (!n || t < tr.t[0] - 2) return null
  if (t <= tr.t[0]) return [tr.u[0], tr.v[0]]
  if (t >= tr.t[n - 1]) return [tr.u[n - 1], tr.v[n - 1]]
  let lo = 0
  let hi = n - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (tr.t[mid] <= t) lo = mid
    else hi = mid
  }
  const span = tr.t[hi] - tr.t[lo]
  if (span > 6) return [tr.u[lo], tr.v[lo]]
  const f = span > 0 ? (t - tr.t[lo]) / span : 0
  return [tr.u[lo] + (tr.u[hi] - tr.u[lo]) * f, tr.v[lo] + (tr.v[hi] - tr.v[lo]) * f]
}

function trail(tr: Track, t: number): string {
  const pts: string[] = []
  for (let i = 0; i < tr.t.length; i++) {
    if (tr.t[i] < t - TRAIL_SECONDS) continue
    if (tr.t[i] > t) break
    pts.push(`${(tr.u[i] * S).toFixed(1)},${(tr.v[i] * S).toFixed(1)}`)
  }
  const now = sample(tr, t)
  if (now) pts.push(`${(now[0] * S).toFixed(1)},${(now[1] * S).toFixed(1)}`)
  return pts.join(' ')
}

export function ReplayPlayer({ replay, meta, theme, autoPlay }: { replay: Replay; meta: MapMeta; theme: 'light' | 'dark'; autoPlay?: boolean }) {
  const data = useMemo(() => buildTracks(replay), [replay])
  const [t, setT] = useState(-3)
  const [playing, setPlaying] = useState(!!autoPlay)
  const [speed, setSpeed] = useState<'1' | '4' | '8'>('4')
  const last = useRef<number | null>(null)

  useEffect(() => { setT(-3); setPlaying(!!autoPlay) }, [replay, autoPlay])
  useEffect(() => { replayClock.set(t) }, [t])

  useEffect(() => {
    if (!playing) return
    let raf = 0
    const step = (now: number) => {
      if (last.current !== null) {
        const dt = ((now - last.current) / 1000) * Number(speed)
        setT((x) => {
          const nx = x + dt
          if (nx >= data.end + 1) { setPlaying(false); return data.end + 1 }
          return nx
        })
      }
      last.current = now
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => { cancelAnimationFrame(raf); last.current = null }
  }, [playing, speed, data])

  const draw: ReplayDraw = useMemo(() => {
    const tokens: ReplayDraw['tokens'] = []
    const trails: ReplayDraw['trails'] = []
    for (let i = 0; i < replay.players.length; i++) {
      const d = data.deathAt.get(i)
      if (d !== undefined && t > d) continue
      const pos = sample(data.tracks[i], t)
      if (!pos) continue
      const pl = replay.players[i]
      tokens.push({ x: pos[0], y: pos[1], side: pl.side, label: agentCode(pl.agent), name: pl.name })
      trails.push({ side: pl.side, points: trail(data.tracks[i], t) })
    }
    const casts = replay.casts
      .filter((c) => c.at && c.t <= t && (c.cat === 'trap' || t - c.t < 10))
      .map((c) => ({ x: c.at![0], y: c.at![1], cat: c.cat, aim: c.cat === 'trap' ? null : c.aim, fade: c.cat === 'trap' ? 0.9 : Math.max(0.2, 1 - (t - c.t) / 10) }))
    const kills = replay.kills
      .filter((k) => k.from && k.to && k.t <= t && t - k.t < 6)
      .map((k) => ({ from: k.from!, to: k.to!, fade: Math.max(0, 1 - (t - k.t) / 6) }))
    const plantEv = replay.events.find((e) => e.type === 'plantBomb' && e.t <= t && e.at)
    return { tokens, trails, casts, kills, plant: plantEv ? plantEv.at : null }
  }, [data, replay, t])

  const toggle = () => {
    if (t >= data.end) setT(-3)
    setPlaying((x) => !x)
  }

  return (
    <>
      <MapView map={replay.map} meta={meta} mode="replay" theme={theme} replay={draw} />
      <div className="replay-bar">
        <button type="button" className="icon-btn solid" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>
          <Icon name={playing ? 'pause' : 'play'} />
        </button>
        <span className="num replay-time">{t < 0 ? 'Buy' : clock(t)}</span>
        <input type="range" min={-3} max={Math.ceil(data.end + 1)} step={0.1} value={t}
               onChange={(e) => { setT(+e.target.value); setPlaying(false) }} aria-label="Round time" />
        <span className="num faint replay-time">{clock(data.end)}</span>
        <Seg label="Playback speed" value={speed} onChange={setSpeed}
             options={[{ id: '1', label: '1×' }, { id: '4', label: '4×' }, { id: '8', label: '8×' }]} />
      </div>
    </>
  )
}

export function ReplayFeed({ replay }: { replay: Replay }) {
  const t = useSyncExternalStore(replayClock.subscribe, () => Math.floor(replayClock.get()))
  const rows = useMemo(() => {
    const out: { t: number; side: string; text: string }[] = []
    for (const k of replay.kills) {
      const a = k.killer !== null ? replay.players[k.killer] : null
      const b = k.victim !== null ? replay.players[k.victim] : null
      out.push({ t: k.t, side: a?.side ?? '', text: `${a?.name ?? 'Unknown'} killed ${b?.name ?? 'unknown'}${k.weapon ? ` with ${k.weapon}` : ''}` })
    }
    for (const e of replay.events) {
      const a = e.p !== null ? replay.players[e.p] : null
      const what = e.type === 'plantBomb' ? 'planted the spike' : e.type === 'defuseBomb' ? 'defused the spike' : 'Spike detonated'
      out.push({ t: e.t, side: a?.side ?? '', text: a ? `${a.name} ${what}` : what })
    }
    return out.sort((x, y) => x.t - y.t)
  }, [replay])
  return (
    <ol className="feed">
      {rows.map((r, i) => (
        <li key={i} data-side={r.side} data-state={r.t <= t ? 'past' : 'future'}>
          <span className="num">{clock(r.t)}</span>
          <span>{r.text}</span>
        </li>
      ))}
    </ol>
  )
}
