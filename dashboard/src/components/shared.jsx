// ── shared.jsx — Componentes y utilidades globales de FerreBot Dashboard ──────
import { createContext, useContext, useState, useEffect } from 'react'
import { motion } from 'framer-motion'

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
  // ── Tema claro: arena cálida + rojo ladrillo ──────────────────────────────
  caramelo: {
    id: 'caramelo',
    label: '☀️ Claro',
    bg:         '#F2EDE4',
    bgPattern:  `radial-gradient(circle at 20% 50%, rgba(212,32,16,0.03) 0%, transparent 50%),
                 radial-gradient(circle at 80% 20%, rgba(212,32,16,0.02) 0%, transparent 40%),
                 #F2EDE4`,
    header:     'rgba(255,253,249,0.92)',
    headerBlur: 'blur(12px)',
    card:       '#FFFFFF',
    cardHover:  '#FDF9F4',
    cardGrad:   'linear-gradient(135deg, #FFFFFF 0%, #FDF9F4 100%)',
    border:     '#E4DDD3',
    borderSoft: '#EDE8E0',
    text:       '#1C1410',
    textSub:    '#4A3F35',
    textMuted:  '#9C8E82',
    accent:     '#D42010',
    accentSub:  'rgba(212,32,16,0.08)',
    accentHov:  '#A81808',
    accentGlow: 'rgba(212,32,16,0.15)',
    green:      '#1A7A3C',
    greenSub:   'rgba(26,122,60,0.08)',
    yellow:     '#C47A10',
    yellowSub:  'rgba(196,122,16,0.08)',
    blue:       '#2056C8',
    blueSub:    'rgba(32,86,200,0.08)',
    tableAlt:   '#FDFAF6',
    tableFoot:  '#F5F0E8',
    shadow:     '0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06)',
    shadowHov:  '0 4px 8px rgba(0,0,0,0.06), 0 12px 32px rgba(0,0,0,0.10)',
    shadowCard: '0 0 0 1px rgba(0,0,0,0.04), 0 2px 8px rgba(0,0,0,0.06)',
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
      position:     'relative',
      background:   t.cardGrad,
      border:       `1px solid ${t.border}`,
      borderRadius: 16,
      padding:      20,
      boxShadow:    t.shadowCard,
      overflow:     'hidden',
      ...style,
    }}>
      {/* Accent line top */}
      <div style={{
        position:   'absolute',
        top:        0, left: 16, right: 16,
        height:     2,
        background: `linear-gradient(90deg, transparent, ${t.accent}40, transparent)`,
        borderRadius: 99,
      }}/>
      {children}
    </div>
  )
}

export function GlassCard({ children, style = {} }) {
  const t = useTheme()
  const isCaramelo = t.id === 'caramelo'
  return (
    <div style={{
      position:       'relative',
      background:     isCaramelo ? 'rgba(255,255,255,0.72)' : t.cardGrad,
      backdropFilter: isCaramelo ? 'blur(12px)'             : undefined,
      WebkitBackdropFilter: isCaramelo ? 'blur(12px)'       : undefined,
      border:         isCaramelo
        ? '0.5px solid rgba(200,32,14,0.12)'
        : `1px solid ${t.border}`,
      borderRadius:   16,
      padding:        20,
      boxShadow:      isCaramelo
        ? '0 2px 12px rgba(0,0,0,0.06), 0 0 0 0.5px rgba(200,32,14,0.08)'
        : t.shadowCard,
      overflow:       'hidden',
      ...style,
    }}>
      {children}
    </div>
  )
}

export function KpiCard({ label, value, sub, color, icon }) {
  const t         = useTheme()
  const c         = color || t.accent
  const isCaramelo = t.id === 'caramelo'

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
      whileHover={{ scale: 1.02 }}
      style={{
        flex: 1, minWidth: 160,
        position: 'relative',
        background: isCaramelo
          ? 'rgba(255,255,255,0.72)'
          : t.cardGrad,
        backdropFilter:       isCaramelo ? 'blur(12px)' : undefined,
        WebkitBackdropFilter: isCaramelo ? 'blur(12px)' : undefined,
        border: isCaramelo
          ? `0.5px solid rgba(200,32,14,0.14)`
          : `1px solid ${t.border}`,
        borderRadius: 16,
        padding: '16px 18px 16px 22px',
        cursor: 'default',
        transition: 'border-color 0.2s ease, box-shadow 0.2s ease, background 0.22s cubic-bezier(0.4,0,0.2,1)',
        boxShadow: isCaramelo
          ? '0 2px 12px rgba(0,0,0,0.07), 0 0 0 0.5px rgba(200,32,14,0.08)'
          : t.shadowCard,
        overflow: 'hidden',
      }}
    >
      {/* Left accent bar */}
      <div style={{
        position: 'absolute',
        left: 0, top: '20%', bottom: '20%',
        width: 3,
        background: `linear-gradient(180deg, ${c}00, ${c}, ${c}00)`,
        borderRadius: 99,
        opacity: 0.6,
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
  const t = useTheme()
  return (
    <h2 style={{
      fontSize:      13,
      fontWeight:    700,
      color:         t.textSub,
      marginBottom:  16,
      paddingBottom: 10,
      borderBottom:  `1px solid ${t.border}`,
      letterSpacing: '.04em',
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
  const t = useTheme()
  const isDark = t.id !== 'caramelo'
  return (
    <div style={{
      background:   isDark ? `${t.accent}10` : '#fef2f2',
      border:       `1px solid ${t.accent}40`,
      borderRadius: 10,
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
  return (
    <span style={{
      display:      'inline-flex',
      alignItems:   'center',
      padding:      '3px 10px',
      borderRadius: 99,
      background:   col + '18',
      color:        col,
      border:       `1px solid ${col}35`,
      fontSize:     10,
      fontWeight:   700,
      letterSpacing: '.04em',
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
        background:   active ? t.accent : t.accentSub,
        border:       `1px solid ${active ? t.accent : t.border}`,
        color:        active ? '#fff' : t.textMuted,
        fontSize:     11,
        padding:      '5px 14px',
        borderRadius: 8,
        cursor:       'pointer',
        fontFamily:   'inherit',
        transition:   'all .15s',
        fontWeight:   active ? 700 : 500,
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
        borderRadius: 9,
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
