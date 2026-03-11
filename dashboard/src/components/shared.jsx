// ── shared.jsx — Componentes y utilidades globales de FerreBot Dashboard ──────
import { createContext, useContext, useState, useEffect } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// TEMAS
// ─────────────────────────────────────────────────────────────────────────────
export const THEMES = {
  dark: {
    id: 'dark',
    label: '🌑 Oscuro',
    bg:         '#0a0a0a',
    header:     '#0d0d0d',
    card:       '#141414',
    cardHover:  '#1e1e1e',
    border:     '#222222',
    borderSoft: '#1a1a1a',
    text:       '#f0e6d8',
    textSub:    '#cccccc',
    textMuted:  '#555555',
    accent:     '#dc2626',
    accentSub:  '#dc262614',
    accentHov:  '#b91c1c',
    green:      '#22c55e',
    yellow:     '#fbbf24',
    blue:       '#60a5fa',
    tableAlt:   '#111111',
    tableFoot:  '#111111',
    shadow:     '0 4px 24px rgba(0,0,0,.6)',
  },
  mid: {
    id: 'mid',
    label: '🌒 Intermedio',
    bg:         '#0f1117',
    header:     '#13161e',
    card:       '#1a1d27',
    cardHover:  '#21253280',
    border:     '#2a2d3a',
    borderSoft: '#1e2130',
    text:       '#e2e8f0',
    textSub:    '#94a3b8',
    textMuted:  '#475569',
    accent:     '#dc2626',
    accentSub:  '#dc262618',
    accentHov:  '#b91c1c',
    green:      '#22c55e',
    yellow:     '#f59e0b',
    blue:       '#818cf8',
    tableAlt:   '#13161e',
    tableFoot:  '#13161e',
    shadow:     '0 4px 24px rgba(0,0,0,.5)',
  },
  light: {
    id: 'light',
    label: '☀️ Claro',
    bg:         '#f1f5f9',
    header:     '#ffffff',
    card:       '#ffffff',
    cardHover:  '#f8fafc',
    border:     '#e2e8f0',
    borderSoft: '#f1f5f9',
    text:       '#0f172a',
    textSub:    '#334155',
    textMuted:  '#94a3b8',
    accent:     '#dc2626',
    accentSub:  '#fef2f2',
    accentHov:  '#b91c1c',
    green:      '#16a34a',
    yellow:     '#d97706',
    blue:       '#3b82f6',
    tableAlt:   '#f8fafc',
    tableFoot:  '#f1f5f9',
    shadow:     '0 2px 16px rgba(0,0,0,.08)',
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// THEME CONTEXT
// ─────────────────────────────────────────────────────────────────────────────
export const ThemeContext = createContext(THEMES.dark)

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
  }, deps)

  return { data, loading, error }
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
  return (
    <Card style={{ flex: 1, minWidth: 160, padding: '16px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 8 }}>
            {label}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: t.text, letterSpacing: '-0.02em' }}>
            {value}
          </div>
          {sub && (
            <div style={{ fontSize: 11, color: c, marginTop: 5 }}>{sub}</div>
          )}
        </div>
        {icon && <span style={{ fontSize: 20, opacity: .65 }}>{icon}</span>}
      </div>
    </Card>
  )
}

export function SectionTitle({ children }) {
  const t = useTheme()
  return (
    <h2 style={{
      fontSize:      14,
      fontWeight:    600,
      color:         t.text,
      marginBottom:  14,
      paddingBottom: 10,
      borderBottom:  `1px solid ${t.border}`,
      letterSpacing: '.01em',
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
  return (
    <div style={{
      background:   t.id === 'light' ? '#fef2f2' : '#1a0808',
      border:       `1px solid ${t.accent}44`,
      borderRadius: 8,
      padding:      '12px 16px',
      color:        t.id === 'light' ? '#dc2626' : '#f87171',
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
      fontSize:      9,
      color:         t.textMuted,
      textTransform: 'uppercase',
      letterSpacing: '.08em',
      fontWeight:    500,
      borderBottom:  `1px solid ${t.border}`,
      whiteSpace:    'nowrap',
    }}>
      {children}
    </th>
  )
}
