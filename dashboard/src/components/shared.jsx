// ── shared.jsx — helpers de datos del dashboard ──────────────────────────────
// Post Fase 5 + limpieza: tras la tokenización completa de todos los tabs,
// este módulo queda como un colector de helpers (formato, API_BASE, fetch,
// detector móvil) + dos componentes tokenizados (Spinner, ErrorMsg) usados
// transversalmente. Los 4 temas legacy (caramelo/forja/brasa/ferrari),
// ThemeContext, useTheme y los componentes con inline-styles fueron
// eliminados — el dashboard depende ahora exclusivamente de los tokens
// semantic en CSS vars (light/dark via `data-theme`).
import { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useAuth.js'

// ─────────────────────────────────────────────────────────────────────────────
// FORMATTERS
// ─────────────────────────────────────────────────────────────────────────────
export function cop(val) {
  if (val === null || val === undefined || isNaN(val)) return '$0'
  return '$' + Math.round(val).toLocaleString('es-CO')
}

export function num(n) {
  if (n === null || n === undefined) return '0'
  return Number(n).toLocaleString('es-CO', { maximumFractionDigits: 2 })
}

// ─────────────────────────────────────────────────────────────────────────────
// API_BASE
// ─────────────────────────────────────────────────────────────────────────────
export const API_BASE = (() => {
  try {
    return import.meta.env.VITE_API_URL || ''
  } catch {
    return ''
  }
})()

// ─────────────────────────────────────────────────────────────────────────────
// useFetch
// ─────────────────────────────────────────────────────────────────────────────
export function useFetch(path, deps = []) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [tick,    setTick]    = useState(0)
  const { authFetch } = useAuth()

  const refetch = () => setTick(t => t + 1)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    authFetch(`${API_BASE}${path}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, loading, error, refetch }
}

// ─────────────────────────────────────────────────────────────────────────────
// SPINNER / ERRORMSG — tokenizados (consumers transversales)
// ─────────────────────────────────────────────────────────────────────────────

export function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
      <div
        className="size-7 rounded-full border-2 border-border animate-spin"
        style={{ borderTopColor: 'hsl(var(--accent))' }}
      />
      <span className="text-xs tracking-wide">Cargando…</span>
    </div>
  )
}

export function ErrorMsg({ msg }) {
  return (
    <div className="bg-destructive/10 border border-destructive/40 rounded-md px-4 py-3 text-sm text-destructive flex items-center gap-2">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="size-4 flex-shrink-0"
      >
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
        <line x1="12" x2="12" y1="9" y2="13" />
        <line x1="12" x2="12.01" y1="17" y2="17" />
      </svg>
      <span>{msg}</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ProductThumb — miniatura cuadrada de producto con fallback a iniciales
// ─────────────────────────────────────────────────────────────────────────────
export function ProductThumb({ src, nombre, size = 32, className = '' }) {
  const iniciales = String(nombre || '?')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() || '')
    .join('') || '?'

  if (src) {
    return (
      <img
        src={src}
        alt={nombre || ''}
        className={`rounded-sm object-cover shrink-0 ${className}`}
        style={{ width: size, height: size }}
      />
    )
  }

  return (
    <span
      aria-hidden="true"
      className={`grid place-items-center rounded-sm bg-surface-2 text-muted-foreground font-semibold shrink-0 ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
    >
      {iniciales}
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// useIsMobile — media query (max-width: 767px) con listener
// ─────────────────────────────────────────────────────────────────────────────
export function useIsMobile() {
  const mq = typeof window !== 'undefined'
    ? window.matchMedia('(max-width: 767px)')
    : null

  const [v, setV] = useState(() => mq ? mq.matches : false)

  useEffect(() => {
    if (!mq) return
    const fn = (e) => setV(e.matches)

    if (mq.addEventListener) {
      mq.addEventListener('change', fn)
    } else {
      mq.addListener(fn)
    }

    const onResize = () => setV(window.matchMedia('(max-width: 767px)').matches)
    window.addEventListener('orientationchange', onResize)
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', onResize)
    }

    setV(window.matchMedia('(max-width: 767px)').matches)

    return () => {
      if (mq.removeEventListener) {
        mq.removeEventListener('change', fn)
      } else {
        mq.removeListener(fn)
      }
      window.removeEventListener('orientationchange', onResize)
      if (window.visualViewport) {
        window.visualViewport.removeEventListener('resize', onResize)
      }
    }
  }, [])

  return v
}
