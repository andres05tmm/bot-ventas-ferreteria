// ── shared.jsx — Componentes y utilidades globales de FerreBot Dashboard ──────
import { createContext, useContext, useState, useEffect } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// TEMAS
// ─────────────────────────────────────────────────────────────────────────────
export const THEMES = {
  // ── Tema claro: arena cálida + rojo ladrillo ──────────────────────────────
  caramelo: {
    id: 'caramelo',
    label: '☀️ Claro',
    bg:         '#F5F0E8',
    header:     '#FFFDF9',
    card:       '#FFFFFF',
    cardHover:  '#FDF8F2',
    border:     '#E8E0D4',
    borderSoft: '#F0EAE0',
    text:       '#1C1410',
    textSub:    '#4A3F35',
    textMuted:  '#9C8E82',
    accent:     '#D42010',
    accentSub:  '#D4201012',
    accentHov:  '#A81808',
    green:      '#1A7A3C',
    yellow:     '#C47A10',
    blue:       '#2056C8',
    tableAlt:   '#FDFAF6',
    tableFoot:  '#F7F2EA',
    shadow:     '0 1px 3px rgba(0,0,0,.06), 0 4px 16px rgba(0,0,0,.06)',
  },
  // ── Tema oscuro: pizarra profunda ─────────────────────────────────────────
  forja: {
    id: 'forja',
    label: '🌙 Oscuro',
    bg:         '#111318',
    header:     '#16191F',
    card:       '#1E2128',
    cardHover:  '#252931',
    border:     '#2C3040',
    borderSoft: '#242834',
    text:       '#EBE6DE',
    textSub:    '#A8A098',
    textMuted:  '#585460',
    accent:     '#E83020',
    accentSub:  '#E8302016',
    accentHov:  '#C02018',
    green:      '#34D060',
    yellow:     '#F0A020',
    blue:       '#6090F8',
    tableAlt:   '#191C24',
    tableFoot:  '#14171E',
    shadow:     '0 2px 8px rgba(0,0,0,.4), 0 8px 32px rgba(0,0,0,.3)',
  },
  // ── Tema medio: carbón con calidez ────────────────────────────────────────
  brasa: {
    id: 'brasa',
    label: '🔥 Brasa',
    bg:         '#0E0C0A',
    header:     '#141210',
    card:       '#1C1916',
    cardHover:  '#242018',
    border:     '#302A24',
    borderSoft: '#261F18',
    text:       '#F0E8DC',
    textSub:    '#C0A890',
    textMuted:  '#705848',
    accent:     '#F03418',
    accentSub:  '#F0341814',
    accentHov:  '#C02810',
    green:      '#40C870',
    yellow:     '#F8A830',
    blue:       '#7098F0',
    tableAlt:   '#181410',
    tableFoot:  '#141008',
    shadow:     '0 2px 8px rgba(0,0,0,.5), 0 8px 32px rgba(240,52,24,.08)',
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// THEME CONTEXT
// ─────────────────────────────────────────────────────────────────────────────
export const ThemeContext = createContext(THEMES.caramelo)

export function useTheme() {
  return useContext(ThemeContext)
}

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
// API_BASE — centralizado aquí para evitar imports circulares
// ─────────────────────────────────────────────────────────────────────────────
export const API_BASE = (() => {
  try {
    return import.meta.env.VITE_API_URL || ''
  } catch {
    return ''
  }
})()

// ─────────────────────────────────────────────────────────────────────────────
// useFetch — acepta deps array para recargar al cambiar refreshKey
// ─────────────────────────────────────────────────────────────────────────────
export function useFetch(path, deps = []) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [tick,    setTick]    = useState(0)

  const refetch = () => setTick(t => t + 1)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}${path}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, loading, error, refetch }
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTES BASE
// ─────────────────────────────────────────────────────────────────────────────

export function Card({ children, style = {} }) {
  const t = useTheme()
  return (
    <div style={{
      background:   t.card,
      border:       `1px solid ${t.border}`,
      borderRadius: 10,
      padding:      20,
      boxShadow:    t.shadow,
      ...style,
    }}>
      {children}
    </div>
  )
}

export function KpiCard({ label, value, sub, color, icon }) {
  const t = useTheme()
  const c = color || t.accent
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flex: 1, minWidth: 160,
        background: t.card,
        border: `1px solid ${hov ? c : t.border}`,
        borderRadius: 12,
        padding: '16px 18px',
        cursor: 'default',
        transition: 'border-color .2s ease, box-shadow .25s ease',
        boxShadow: hov
          ? `0 0 0 3px ${c}44, 0 0 12px ${c}22`
          : 'none',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: t.textSub, letterSpacing: '.02em', marginBottom: 10 }}>
            {label}
          </div>
          <div style={{
            fontSize: hov ? 24 : 20,
            fontWeight: 400,
            color: hov ? c : t.text,
            letterSpacing: '-0.02em',
            fontVariantNumeric: 'tabular-nums',
            transition: 'font-size .2s ease, color .2s ease',
          }}>
            {value}
          </div>
          {sub && (
            <div style={{ fontSize: 11, color: c, marginTop: 6 }}>{sub}</div>
          )}
        </div>
        {icon && (
          <span style={{
            fontSize: 20,
            opacity: hov ? 1 : .5,
            transition: 'opacity .2s ease, transform .2s ease',
            transform: hov ? 'scale(1.15)' : 'scale(1)',
            display: 'inline-block',
          }}>{icon}</span>
        )}
      </div>
    </div>
  )
}

export function SectionTitle({ children }) {
  const t = useTheme()
  return (
    <h2 style={{
      fontSize:      14,
      fontWeight:    500,
      color:         t.textSub,
      marginBottom:  14,
      paddingBottom: 10,
      borderBottom:  `1px solid ${t.border}`,
      letterSpacing: '.02em',
    }}>
      {children}
    </h2>
  )
}

export function Spinner() {
  const t = useTheme()
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 48, color: t.textMuted, gap: 10 }}>
      <div style={{
        width: 18, height: 18,
        border: `2px solid ${t.border}`,
        borderTopColor: t.accent,
        borderRadius: '50%',
        animation: 'spin .7s linear infinite',
      }} />
      <span style={{ fontSize: 12 }}>Cargando...</span>
    </div>
  )
}

export function ErrorMsg({ msg }) {
  const t = useTheme()
  const isDark = ['dark','mid'].includes(t.id)
  return (
    <div style={{
      background:   isDark ? '#1a0808' : '#fef2f2',
      border:       `1px solid ${t.accent}44`,
      borderRadius: 8,
      padding:      '12px 16px',
      color:        isDark ? '#f87171' : t.accent,
      fontSize:     13,
    }}>
      ⚠️ {msg}
    </div>
  )
}

export function EmptyState({ msg = 'Sin datos para este período.' }) {
  const t = useTheme()
  return (
    <div style={{ padding: '32px 24px', textAlign: 'center', color: t.textMuted, fontSize: 12 }}>
      {msg}
    </div>
  )
}

export function Badge({ children, color }) {
  const t   = useTheme()
  const col = color || t.accent
  return (
    <span style={{
      display:      'inline-block',
      padding:      '2px 9px',
      borderRadius: 99,
      background:   col + '22',
      color:        col,
      border:       `1px solid ${col}44`,
      fontSize:     10,
      fontWeight:   600,
      whiteSpace:   'nowrap',
    }}>
      {children}
    </span>
  )
}

export function PeriodBtn({ children, active, onClick }) {
  const t = useTheme()
  return (
    <button
      onClick={onClick}
      style={{
        background:   active ? t.accent : 'transparent',
        border:       `1px solid ${active ? t.accent : t.border}`,
        color:        active ? '#fff' : t.textMuted,
        fontSize:     11,
        padding:      '5px 14px',
        borderRadius: 7,
        cursor:       'pointer',
        fontFamily:   'inherit',
        transition:   'all .15s',
        fontWeight:   active ? 600 : 400,
      }}
      onMouseEnter={e => { if (!active) { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.color = t.text } }}
      onMouseLeave={e => { if (!active) { e.currentTarget.style.borderColor = t.border;  e.currentTarget.style.color = t.textMuted } }}
    >
      {children}
    </button>
  )
}

export function StyledInput({ value, onChange, placeholder, style = {} }) {
  const t = useTheme()
  return (
    <input
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      style={{
        background:   t.card,
        border:       `1px solid ${t.border}`,
        color:        t.text,
        padding:      '7px 12px',
        borderRadius: 7,
        fontSize:     11,
        outline:      'none',
        fontFamily:   'inherit',
        transition:   'border-color .15s',
        ...style,
      }}
      onFocus={e => e.currentTarget.style.borderColor = t.accent + '88'}
      onBlur={e  => e.currentTarget.style.borderColor = t.border}
    />
  )
}

export function Th({ children, center, right }) {
  const t = useTheme()
  return (
    <th style={{
      padding:       '9px 14px',
      textAlign:     center ? 'center' : right ? 'right' : 'left',
      fontSize:      10,
      color:         t.textSub,
      textTransform: 'uppercase',
      letterSpacing: '.05em',
      fontWeight:    600,
      borderBottom:  `1px solid ${t.border}`,
      whiteSpace:    'nowrap',
    }}>
      {children}
    </th>
  )
}

// ── Hook detección móvil — exportado para todos los tabs ─────────────────────
export function useIsMobile() {
  // matchMedia es más confiable que innerWidth en PWA Android —
  // innerWidth puede reportar el valor pre-viewport en el primer render.
  const mq = typeof window !== 'undefined'
    ? window.matchMedia('(max-width: 767px)')
    : null

  const [v, setV] = useState(() => mq ? mq.matches : false)

  useEffect(() => {
    if (!mq) return
    const fn = (e) => setV(e.matches)

    // API moderna (Chrome 79+, Safari 14+)
    if (mq.addEventListener) {
      mq.addEventListener('change', fn)
    } else {
      mq.addListener(fn)   // fallback legacy
    }

    // También escuchar orientationchange y visualViewport
    // por si el PWA reporta el viewport tarde al arrancar
    const onResize = () => setV(window.matchMedia('(max-width: 767px)').matches)
    window.addEventListener('orientationchange', onResize)
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', onResize)
    }

    // Re-check al montar (por si el valor inicial fue incorrecto)
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
