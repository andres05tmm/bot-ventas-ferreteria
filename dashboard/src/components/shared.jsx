// ── shared.jsx — Componentes y utilidades globales de FerreBot Dashboard ──────
import { createContext, useContext, useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from '../hooks/useAuth.js'

// ─────────────────────────────────────────────────────────────────────────────
// useCountUp — anima un número de 0 al target en `duration` ms (easeOut cúbico)
// ─────────────────────────────────────────────────────────────────────────────
export function useCountUp(target, duration = 800) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (target === null || target === undefined || target === 0) {
      setVal(0)
      return
    }
    let rafId
    const start = performance.now()
    const step = (now) => {
      const elapsed  = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased    = 1 - Math.pow(1 - progress, 3)
      setVal(target * eased)
      if (progress < 1) rafId = requestAnimationFrame(step)
    }
    rafId = requestAnimationFrame(step)
    return () => cancelAnimationFrame(rafId)
  }, [target, duration])
  return val
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMAS
// ─────────────────────────────────────────────────────────────────────────────
export const THEMES = {
  // ── Tema Ferrari: editorial negro/blanco + rojo Rosso Corsa ───────────────
  ferrari: {
    id: 'ferrari',
    label: '◆ Ferrari',
    bg:         '#FFFFFF',
    bgPattern:  '#FFFFFF',
    header:     '#000000',
    headerBlur: 'none',
    card:       '#FFFFFF',
    cardHover:  '#FFFFFF',
    cardGrad:   '#FFFFFF',
    border:     '#CCCCCC',
    borderSoft: '#D2D2D2',
    text:       '#181818',
    textSub:    '#666666',
    textMuted:  '#8F8F8F',
    accent:     '#DA291C',
    accentSub:  'rgba(218,41,28,0.06)',
    accentHov:  '#B01E0A',
    accentGlow: 'rgba(218,41,28,0.12)',
    green:      '#03904A',
    greenSub:   'rgba(3,144,74,0.08)',
    yellow:     '#F6E500',
    yellowSub:  'rgba(246,229,0,0.10)',
    blue:       '#4C98B9',
    blueSub:    'rgba(76,152,185,0.10)',
    tableAlt:   '#F8F8F8',
    tableFoot:  '#F0F0F0',
    shadow:     'none',
    shadowHov:  'none',
    shadowCard: 'none',
    radius:     2,
  },
  // ── Tema claro: arena cálida + rojo ladrillo ──────────────────────────────
  caramelo: {
    id: 'caramelo',
    label: '☀️ Claro',
    bg:         '#F8F5F1',
    bgPattern:  `radial-gradient(circle at 20% 50%, rgba(200,32,14,0.03) 0%, transparent 50%),
                 radial-gradient(circle at 80% 20%, rgba(200,32,14,0.02) 0%, transparent 40%),
                 #F8F5F1`,
    header:     'rgba(255,254,252,0.96)',
    headerBlur: 'blur(20px)',
    card:       '#FFFFFF',
    cardHover:  '#FEFCF9',
    cardGrad:   'linear-gradient(135deg, #FFFFFF 0%, #FEFCF9 100%)',
    border:     '#EAE4DC',
    borderSoft: '#F0EBE3',
    text:       '#1C1410',
    textSub:    '#4A3F35',
    textMuted:  '#9C8E82',
    accent:     '#C8200E',
    accentSub:  'rgba(200,32,14,0.08)',
    accentHov:  '#A01808',
    accentGlow: 'rgba(200,32,14,0.15)',
    green:      '#1A7A3C',
    greenSub:   'rgba(26,122,60,0.08)',
    yellow:     '#C47A10',
    yellowSub:  'rgba(196,122,16,0.08)',
    blue:       '#2056C8',
    blueSub:    'rgba(32,86,200,0.08)',
    tableAlt:   '#FDFAF6',
    tableFoot:  '#F5F0E8',
    shadow:     '0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.07)',
    shadowHov:  '0 8px 28px rgba(0,0,0,0.13), 0 3px 10px rgba(0,0,0,0.07)',
    shadowCard: '0 0 0 1px rgba(0,0,0,0.05), 0 2px 8px rgba(0,0,0,0.07)',
  },
  // ── Tema oscuro: pizarra profunda ─────────────────────────────────────────
  forja: {
    id: 'forja',
    label: '🌙 Oscuro',
    bg:         '#0D1117',
    bgPattern:  `radial-gradient(ellipse at 10% 20%, rgba(232,48,32,0.06) 0%, transparent 40%),
                 radial-gradient(ellipse at 90% 80%, rgba(96,144,248,0.04) 0%, transparent 40%),
                 #0D1117`,
    header:     'rgba(22,27,34,0.90)',
    headerBlur: 'blur(16px)',
    card:       '#161B22',
    cardHover:  '#1C2128',
    cardGrad:   'linear-gradient(135deg, #161B22 0%, #1C2128 100%)',
    border:     '#21262D',
    borderSoft: '#1A1F26',
    text:       '#E6EDF3',
    textSub:    '#8B949E',
    textMuted:  '#484F58',
    accent:     '#E83020',
    accentSub:  'rgba(232,48,32,0.12)',
    accentHov:  '#C02018',
    accentGlow: 'rgba(232,48,32,0.20)',
    green:      '#3FB950',
    greenSub:   'rgba(63,185,80,0.10)',
    yellow:     '#D29922',
    yellowSub:  'rgba(210,153,34,0.10)',
    blue:       '#58A6FF',
    blueSub:    'rgba(88,166,255,0.10)',
    tableAlt:   '#111318',
    tableFoot:  '#0D1117',
    shadow:     '0 1px 0 rgba(255,255,255,0.04), 0 4px 24px rgba(0,0,0,0.40)',
    shadowHov:  '0 0 0 1px rgba(232,48,32,0.20), 0 8px 32px rgba(0,0,0,0.50)',
    shadowCard: '0 0 0 1px rgba(255,255,255,0.05), 0 4px 16px rgba(0,0,0,0.30)',
  },
  // ── Tema medio: carbón con calidez ────────────────────────────────────────
  brasa: {
    id: 'brasa',
    label: '🔥 Brasa',
    bg:         '#100C08',
    bgPattern:  `radial-gradient(ellipse at 15% 30%, rgba(240,52,24,0.08) 0%, transparent 45%),
                 radial-gradient(ellipse at 85% 70%, rgba(240,52,24,0.05) 0%, transparent 40%),
                 #100C08`,
    header:     'rgba(20,18,16,0.92)',
    headerBlur: 'blur(12px)',
    card:       '#1C1714',
    cardHover:  '#231E1A',
    cardGrad:   'linear-gradient(135deg, #1C1714 0%, #211C18 100%)',
    border:     '#2E2620',
    borderSoft: '#241E18',
    text:       '#F0E8DC',
    textSub:    '#C0A890',
    textMuted:  '#6A5040',
    accent:     '#F03418',
    accentSub:  'rgba(240,52,24,0.12)',
    accentHov:  '#C02810',
    accentGlow: 'rgba(240,52,24,0.25)',
    green:      '#40C870',
    greenSub:   'rgba(64,200,112,0.10)',
    yellow:     '#F8A830',
    yellowSub:  'rgba(248,168,48,0.10)',
    blue:       '#7098F0',
    blueSub:    'rgba(112,152,240,0.10)',
    tableAlt:   '#181410',
    tableFoot:  '#120E0A',
    shadow:     '0 1px 0 rgba(255,255,255,0.03), 0 4px 20px rgba(0,0,0,0.50)',
    shadowHov:  '0 0 0 1px rgba(240,52,24,0.25), 0 8px 32px rgba(240,52,24,0.12)',
    shadowCard: '0 0 0 1px rgba(255,255,255,0.04), 0 4px 20px rgba(0,0,0,0.40)',
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
// COMPONENTES BASE
// ─────────────────────────────────────────────────────────────────────────────

export function Card({ children, style = {} }) {
  const t         = useTheme()
  const isFerrari = t.id === 'ferrari'
  const r         = t.radius ?? 16
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position:     'relative',
        background:   t.cardGrad,
        border:       `1px solid ${hovered ? t.accent + '30' : t.border}`,
        borderRadius: r,
        padding:      20,
        boxShadow:    hovered ? t.shadowHov : t.shadowCard,
        overflow:     'hidden',
        transform:    (hovered && !isFerrari) ? 'translateY(-2px)' : 'translateY(0)',
        transition:   'transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease',
        ...style,
      }}
    >
      {/* Accent line top — solo en temas no-ferrari */}
      {!isFerrari && (
        <div style={{
          position:   'absolute',
          top:        0, left: 16, right: 16,
          height:     2,
          background: `linear-gradient(90deg, transparent, ${t.accent}${hovered ? '60' : '40'}, transparent)`,
          borderRadius: 99,
          transition: 'opacity 0.22s ease',
        }}/>
      )}
      {children}
    </div>
  )
}

export function GlassCard({ children, style = {} }) {
  const t         = useTheme()
  const isCaramelo = t.id === 'caramelo'
  const isFerrari  = t.id === 'ferrari'
  const r          = t.radius ?? 16
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position:       'relative',
        background:     isCaramelo
          ? (hovered ? 'rgba(255,255,255,0.88)' : 'rgba(255,255,255,0.72)')
          : t.cardGrad,
        backdropFilter: isCaramelo ? 'blur(16px)'       : undefined,
        WebkitBackdropFilter: isCaramelo ? 'blur(16px)' : undefined,
        border:         isCaramelo
          ? `0.5px solid rgba(200,32,14,${hovered ? '0.22' : '0.12'})`
          : `1px solid ${hovered ? t.accent + '40' : t.border}`,
        borderRadius:   r,
        padding:        20,
        boxShadow:      isCaramelo
          ? (hovered
              ? '0 8px 28px rgba(0,0,0,0.12), 0 0 0 0.5px rgba(200,32,14,0.18)'
              : '0 2px 12px rgba(0,0,0,0.06), 0 0 0 0.5px rgba(200,32,14,0.08)')
          : (hovered ? t.shadowHov : t.shadowCard),
        overflow:       'hidden',
        transform:      (hovered && !isFerrari) ? 'translateY(-2px)' : 'translateY(0)',
        transition:     'transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease, background 0.22s ease',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function KpiCard({ label, value, sub, color, icon }) {
  const t          = useTheme()
  const c          = color || t.accent
  const isCaramelo = t.id === 'caramelo'
  const isFerrari  = t.id === 'ferrari'
  const r          = t.radius ?? 16
  const [hovered, setHovered] = useState(false)

  // Count-up: parse numeric value from formatted string or raw number
  const rawNum = (() => {
    if (typeof value === 'number') return value
    if (typeof value !== 'string') return null
    // strip $ and Colombian thousands sep (dots), keep digits
    const cleaned = value.replace(/\$/g, '').replace(/\./g, '').replace(/,.*$/, '').trim()
    const n = parseInt(cleaned, 10)
    return isNaN(n) ? null : n
  })()
  const animated  = useCountUp(rawNum ?? 0, 800)
  const displayVal = rawNum !== null
    ? (typeof value === 'string' && value.startsWith('$')
        ? '$' + Math.round(animated).toLocaleString('es-CO')
        : Math.round(animated).toLocaleString('es-CO'))
    : value

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      whileHover={isFerrari ? undefined : { scale: 1.025, y: -3 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: 1, minWidth: 160,
        position: 'relative',
        background: isCaramelo
          ? (hovered ? 'rgba(255,255,255,0.92)' : 'rgba(255,255,255,0.72)')
          : t.cardGrad,
        backdropFilter:       isCaramelo ? 'blur(16px)' : undefined,
        WebkitBackdropFilter: isCaramelo ? 'blur(16px)' : undefined,
        border: isCaramelo
          ? `0.5px solid rgba(200,32,14,${hovered ? '0.28' : '0.14'})`
          : `1px solid ${hovered ? t.accent + '40' : t.border}`,
        borderRadius: r,
        padding: '16px 18px 16px 22px',
        cursor: 'default',
        transition: 'border-color 0.22s ease, box-shadow 0.22s ease, background 0.22s ease',
        boxShadow: isCaramelo
          ? (hovered
              ? `0 8px 28px rgba(0,0,0,0.13), 0 0 0 1px ${c}22`
              : '0 2px 12px rgba(0,0,0,0.07), 0 0 0 0.5px rgba(200,32,14,0.08)')
          : (hovered ? t.shadowHov : t.shadowCard),
        overflow: 'hidden',
      }}
    >
      {/* Left accent bar — barra vertical de acento */}
      <div style={{
        position: 'absolute',
        left: 0, top: isFerrari ? 0 : '20%', bottom: isFerrari ? 0 : '20%',
        width: isFerrari ? 2 : 3,
        background: isFerrari ? c : `linear-gradient(180deg, ${c}00, ${c}, ${c}00)`,
        borderRadius: 0,
        opacity: isFerrari ? (hovered ? 1 : 0.7) : (hovered ? 0.9 : 0.55),
        transition: 'opacity 0.22s ease',
      }}/>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{
            fontSize: 10, fontWeight: 600, color: t.textMuted,
            letterSpacing: '.06em', textTransform: 'uppercase',
            marginBottom: 10,
          }}>
            {label}
          </div>
          <div style={{
            fontSize: 24,
            fontWeight: 700,
            color: t.text,
            letterSpacing: '-0.03em',
            fontVariantNumeric: 'tabular-nums',
            lineHeight: 1.1,
          }}>
            {displayVal}
          </div>
          {sub && (
            <div style={{
              fontSize: 11, color: c, marginTop: 7,
              fontWeight: 500, opacity: 0.85,
            }}>{sub}</div>
          )}
        </div>
        {icon && (
          <div style={{
            width: 36, height: 36,
            borderRadius: 10,
            background: isCaramelo ? `${c}12` : t.accentSub,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18,
            flexShrink: 0,
          }}>{icon}</div>
        )}
      </div>
    </motion.div>
  )
}

export function SectionTitle({ children }) {
  const t         = useTheme()
  const isFerrari = t.id === 'ferrari'
  return (
    <h2 style={{
      fontSize:      isFerrari ? 11 : 13,
      fontWeight:    isFerrari ? 400 : 700,
      color:         t.textMuted,
      marginBottom:  16,
      paddingBottom: 10,
      borderBottom:  `1px solid ${t.border}`,
      letterSpacing: isFerrari ? '1px' : '.04em',
      textTransform: 'uppercase',
      display:       'flex',
      alignItems:    'center',
      gap:           8,
    }}>
      {children}
    </h2>
  )
}

export function Spinner() {
  const t = useTheme()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, color: t.textMuted, gap: 12 }}>
      <div style={{
        width: 28, height: 28,
        border: `2px solid ${t.border}`,
        borderTopColor: t.accent,
        borderRadius: '50%',
        animation: 'spin .65s linear infinite',
      }} />
      <span style={{ fontSize: 12, letterSpacing: '.04em' }}>Cargando...</span>
    </div>
  )
}

export function ErrorMsg({ msg }) {
  const t         = useTheme()
  const isDark    = t.id !== 'caramelo' && t.id !== 'ferrari'
  const r         = t.radius ?? 10
  return (
    <div style={{
      background:   isDark ? `${t.accent}10` : '#fef2f2',
      border:       `1px solid ${t.accent}40`,
      borderRadius: r,
      padding:      '12px 16px',
      color:        isDark ? '#f87171' : t.accent,
      fontSize:     13,
      display:      'flex',
      alignItems:   'center',
      gap:          8,
    }}>
      <span style={{ fontSize: 16 }}>⚠️</span>
      {msg}
    </div>
  )
}

export function EmptyState({ msg = 'Sin datos para este período.' }) {
  const t = useTheme()
  return (
    <div style={{
      padding: '40px 24px', textAlign: 'center',
      color: t.textMuted, fontSize: 12,
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
    }}>
      <div style={{ fontSize: 28, opacity: 0.4 }}>📭</div>
      <span>{msg}</span>
    </div>
  )
}

export function Badge({ children, color }) {
  const t   = useTheme()
  const col = color || t.accent
  const r   = t.radius ?? 99
  return (
    <span style={{
      display:       'inline-flex',
      alignItems:    'center',
      padding:       '3px 10px',
      borderRadius:  r,
      background:    col + '18',
      color:         col,
      border:        `1px solid ${col}35`,
      fontSize:      10,
      fontWeight:    t.id === 'ferrari' ? 400 : 700,
      letterSpacing: t.id === 'ferrari' ? '1px' : '.04em',
      textTransform: t.id === 'ferrari' ? 'uppercase' : undefined,
      whiteSpace:    'nowrap',
    }}>
      {children}
    </span>
  )
}

export function PeriodBtn({ children, active, onClick }) {
  const t = useTheme()
  const r = t.radius ?? 8
  return (
    <button
      onClick={onClick}
      style={{
        background:    active ? t.accent : 'transparent',
        border:        `1px solid ${active ? t.accent : t.border}`,
        color:         active ? '#fff' : t.textMuted,
        fontSize:      11,
        padding:       '5px 14px',
        borderRadius:  r,
        cursor:        'pointer',
        fontFamily:    'inherit',
        transition:    'all .15s',
        fontWeight:    active ? 700 : 400,
        letterSpacing: t.id === 'ferrari' ? '0.05em' : undefined,
      }}
      onMouseEnter={e => { if (!active) { e.currentTarget.style.borderColor = t.accent + '60'; e.currentTarget.style.color = t.text } }}
      onMouseLeave={e => { if (!active) { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted } }}
    >
      {children}
    </button>
  )
}

export function StyledInput({ value, onChange, placeholder, style = {} }) {
  const t = useTheme()
  const isMob = typeof window !== 'undefined' && window.screen &&
    Math.min(window.screen.width, window.screen.height) < 768
  return (
    <input
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      style={{
        background:   t.card,
        border:       `1px solid ${t.border}`,
        color:        t.text,
        padding:      '8px 12px',
        borderRadius: t.radius ?? 9,
        fontSize:     isMob ? 16 : 12,
        outline:      'none',
        fontFamily:   'inherit',
        transition:   'border-color .15s, box-shadow .15s',
        ...style,
      }}
      onFocus={e => {
        e.currentTarget.style.borderColor = t.accent + '80'
        e.currentTarget.style.boxShadow = `0 0 0 3px ${t.accent}15`
      }}
      onBlur={e => {
        e.currentTarget.style.borderColor = t.border
        e.currentTarget.style.boxShadow = 'none'
      }}
    />
  )
}

export function Th({ children, center, right }) {
  const t = useTheme()
  return (
    <th style={{
      padding:       '10px 14px',
      textAlign:     center ? 'center' : right ? 'right' : 'left',
      fontSize:      10,
      color:         t.textMuted,
      textTransform: 'uppercase',
      letterSpacing: '.06em',
      fontWeight:    700,
      borderBottom:  `1px solid ${t.border}`,
      whiteSpace:    'nowrap',
    }}>
      {children}
    </th>
  )
}

// ── Hook detección móvil ──────────────────────────────────────────────────────
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
