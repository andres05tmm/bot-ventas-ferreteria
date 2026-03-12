import { useState, useEffect, useCallback } from 'react'
import { ThemeContext, THEMES, useTheme } from './components/shared.jsx'
import TabResumen      from './tabs/TabResumen.jsx'
import TabTopProductos from './tabs/TabTopProductos.jsx'
import TabInventario   from './tabs/TabInventario.jsx'
import TabHistorial    from './tabs/TabHistorial.jsx'
import TabCaja         from './tabs/TabCaja.jsx'
import TabGastos       from './tabs/TabGastos.jsx'
import TabCompras      from './tabs/TabCompras.jsx'
import TabCatalogo     from './tabs/TabCatalogo.jsx'
import TabKardex          from './tabs/TabKardex.jsx'
import TabResultados      from './tabs/TabResultados.jsx'
import TabVentasRapidas   from './tabs/TabVentasRapidas.jsx'

// ── API_BASE exportado para que los tabs lo importen desde aquí ───────────────
export const API_BASE = import.meta.env.VITE_API_URL || ''

// ── Opciones de auto-refresh ──────────────────────────────────────────────────
const REFRESH_OPTIONS = [
  { label: 'Off',   value: 0   },
  { label: '30s',   value: 30  },
  { label: '1min',  value: 60  },
  { label: '5min',  value: 300 },
]

const TABS = ['Resumen', 'Top 10', 'Inventario', 'Historial', 'Caja', 'Gastos', 'Compras', 'Catálogo', 'Kárdex', 'Resultados', 'Ventas Rápidas']
const TAB_ICONS = {
  Resumen: '📊', 'Top 10': '🏆', Inventario: '📦', Historial: '🧾',
  Caja: '💰', Gastos: '💸', Compras: '🚚', 'Catálogo': '🏷️',
  'Kárdex': '📋', 'Resultados': '📈', 'Ventas Rápidas': '⚡',
}

// ─────────────────────────────────────────────────────────────────────────────
// HEADER
// ─────────────────────────────────────────────────────────────────────────────
function Header({ themeId, setThemeId, refreshInterval, setRefreshInterval,
                  lastRefresh, onRefresh, countdown }) {
  const t = useTheme()
  return (
    <div style={{
      borderBottom:   `1px solid ${t.border}`,
      padding:        '0 22px',
      display:        'flex',
      alignItems:     'center',
      justifyContent: 'space-between',
      height:         54,
      background:     t.header,
      position:       'sticky',
      top:            0,
      zIndex:         20,
      boxShadow:      t.shadow,
      gap:            12,
    }}>
      {/* Marca */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <div style={{
          width: 30, height: 30, background: t.accent, borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15,
          boxShadow: `0 0 10px ${t.accent}55`,
        }}>🔩</div>
        <div>
          <span style={{ fontWeight: 700, fontSize: 14, color: t.id === 'light' ? t.text : '#fff' }}>FERRETERÍA</span>
          <span style={{ fontWeight: 700, fontSize: 14, color: t.accent }}> PUNTO ROJO</span>
        </div>
        <div style={{ width: 1, height: 18, background: t.border }} />
        <span style={{ fontSize: 10, color: t.textMuted, letterSpacing: '.1em', textTransform: 'uppercase' }}>Dashboard</span>
      </div>

      {/* Controles */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>

        {/* Timestamp + countdown */}
        {lastRefresh && (
          <div style={{ fontSize: 10, color: t.textMuted, display: 'flex', alignItems: 'center', gap: 5 }}>
            <span>🕐</span>
            <span>{lastRefresh}</span>
            {refreshInterval > 0 && countdown > 0 && (
              <span style={{
                background: t.accentSub, color: t.accent,
                border: `1px solid ${t.accent}44`, borderRadius: 99,
                padding: '1px 7px', fontSize: 9, fontWeight: 700,
              }}>
                {countdown}s
              </span>
            )}
          </div>
        )}

        {/* Refresh manual */}
        <button
          onClick={onRefresh}
          title="Actualizar ahora"
          style={{
            background: t.accentSub, border: `1px solid ${t.accent}44`,
            color: t.accent, borderRadius: 7, padding: '5px 10px',
            fontSize: 14, cursor: 'pointer', fontFamily: 'inherit', transition: 'all .15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = t.accent; e.currentTarget.style.color = '#fff' }}
          onMouseLeave={e => { e.currentTarget.style.background = t.accentSub; e.currentTarget.style.color = t.accent }}
        >↺</button>

        {/* Auto-refresh */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: 10, color: t.textMuted }}>Auto:</span>
          <div style={{ display: 'flex', gap: 3 }}>
            {REFRESH_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setRefreshInterval(opt.value)}
                style={{
                  background:   refreshInterval === opt.value ? t.accent : 'transparent',
                  border:       `1px solid ${refreshInterval === opt.value ? t.accent : t.border}`,
                  color:        refreshInterval === opt.value ? '#fff' : t.textMuted,
                  fontSize:     10, padding: '3px 8px', borderRadius: 5,
                  cursor: 'pointer', fontFamily: 'inherit', transition: 'all .15s',
                }}
              >{opt.label}</button>
            ))}
          </div>
        </div>

        <div style={{ width: 1, height: 18, background: t.border }} />

        {/* Selector de tema */}
        <div style={{ display: 'flex', gap: 3 }}>
          {Object.values(THEMES).map(th => (
            <button
              key={th.id}
              onClick={() => setThemeId(th.id)}
              title={th.label}
              style={{
                background:   themeId === th.id ? t.accent : 'transparent',
                border:       `1px solid ${themeId === th.id ? t.accent : t.border}`,
                color:        themeId === th.id ? '#fff' : t.textMuted,
                fontSize:     11, padding: '3px 8px', borderRadius: 5,
                cursor: 'pointer', fontFamily: 'inherit', transition: 'all .15s',
              }}
            >{th.label.split(' ')[0]}</button>
          ))}
        </div>

        <div style={{ width: 1, height: 18, background: t.border }} />

        {/* Estado bot + fecha */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ fontSize: 10, color: t.textMuted }}>
            <span style={{ color: '#4ade80' }}>●</span> Bot activo
          </div>
          <div style={{ fontSize: 10, color: t.textMuted }}>
            {new Date().toLocaleDateString('es-CO', { weekday: 'short', day: 'numeric', month: 'short' })}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TABS NAV
// ─────────────────────────────────────────────────────────────────────────────
function TabsNav({ activeTab, setTab }) {
  const t = useTheme()
  return (
    <div style={{
      padding:      '0 22px',
      display:      'flex',
      gap:          2,
      borderBottom: `1px solid ${t.border}`,
      background:   t.header,
      position:     'sticky',
      top:          54,
      zIndex:       19,
    }}>
      {TABS.map(tab => {
        const active = activeTab === tab
        return (
          <button
            key={tab}
            onClick={() => setTab(tab)}
            style={{
              background:   active ? t.accentSub : 'transparent',
              border:       'none',
              borderBottom: `2px solid ${active ? t.accent : 'transparent'}`,
              color:        active ? t.accent : t.textMuted,
              fontSize:     12, padding: '10px 16px',
              cursor: 'pointer', fontFamily: 'inherit',
              fontWeight: active ? 600 : 400,
              borderRadius: '6px 6px 0 0', transition: 'all .15s',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
            onMouseEnter={e => { if (!active) { e.currentTarget.style.color = t.textSub } }}
            onMouseLeave={e => { if (!active) { e.currentTarget.style.color = t.textMuted } }}
          >
            <span>{TAB_ICONS[tab]}</span>
            <span>{tab}</span>
          </button>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// APP SHELL
// ─────────────────────────────────────────────────────────────────────────────
function AppShell({ themeId, setThemeId }) {
  const t = useTheme()
  const [tab,             setTab]             = useState('Resumen')
  const [refreshInterval, setRefreshInterval] = useState(0)
  const [refreshKey,      setRefreshKey]      = useState(0)
  const [lastRefresh,     setLastRefresh]     = useState('')
  const [countdown,       setCountdown]       = useState(0)

  const stamp = () => new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  const doRefresh = useCallback(() => {
    setRefreshKey(k => k + 1)
    setLastRefresh(stamp())
    if (refreshInterval > 0) setCountdown(refreshInterval)
  }, [refreshInterval])

  // Registrar hora de carga inicial
  useEffect(() => { setLastRefresh(stamp()) }, [])

  // Auto-refresh countdown
  useEffect(() => {
    if (refreshInterval === 0) { setCountdown(0); return }
    setCountdown(refreshInterval)
    const tick = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) {
          setRefreshKey(k => k + 1)
          setLastRefresh(stamp())
          return refreshInterval
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [refreshInterval])

  return (
    <div style={{
      fontFamily: "'DM Sans', 'Geist', system-ui, sans-serif",
      background: t.bg,
      minHeight:  '100vh',
      color:      t.text,
      fontSize:   13,
      transition: 'background .3s, color .3s',
    }}>
      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0 }
        button { font-family: inherit }
        button:focus, input:focus { outline: none }
        input::placeholder { color: ${t.textMuted}; opacity: 1 }
        @keyframes spin  { to { transform: rotate(360deg) } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        ::-webkit-scrollbar       { width:4px; height:4px }
        ::-webkit-scrollbar-track { background: ${t.bg} }
        ::-webkit-scrollbar-thumb { background: ${t.accent}; border-radius: 2px }
      `}</style>

      <Header
        themeId={themeId}           setThemeId={setThemeId}
        refreshInterval={refreshInterval} setRefreshInterval={setRefreshInterval}
        lastRefresh={lastRefresh}   onRefresh={doRefresh}
        countdown={countdown}
      />
      <TabsNav activeTab={tab} setTab={setTab} />

      <div style={{ padding: '20px 22px', maxWidth: 1280, margin: '0 auto' }}>
        {tab === 'Resumen'    && <TabResumen      refreshKey={refreshKey} />}
        {tab === 'Top 10'     && <TabTopProductos refreshKey={refreshKey} />}
        {tab === 'Inventario' && <TabInventario   refreshKey={refreshKey} />}
        {tab === 'Historial'  && <TabHistorial    refreshKey={refreshKey} />}
        {tab === 'Caja'       && <TabCaja         refreshKey={refreshKey} />}
        {tab === 'Gastos'     && <TabGastos       refreshKey={refreshKey} />}
        {tab === 'Compras'    && <TabCompras      refreshKey={refreshKey} />}
        {tab === 'Catálogo'   && <TabCatalogo     refreshKey={refreshKey} />}
        {tab === 'Kárdex'     && <TabKardex       refreshKey={refreshKey} />}
        {tab === 'Resultados'      && <TabResultados   refreshKey={refreshKey} />}
        {tab === 'Ventas Rápidas'  && <TabVentasRapidas refreshKey={refreshKey} />}
      </div>

      <div style={{
        borderTop: `1px solid ${t.border}`, padding: '10px 22px', marginTop: 20,
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: 10, color: t.textMuted }}>Ferretería Punto Rojo · Dashboard v5</span>
        <span style={{ fontSize: 10, color: t.textMuted }}>Google Sheets · Excel · memoria.json</span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ROOT — provee ThemeContext dinámicamente
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const [themeId, setThemeId] = useState('dark')
  return (
    <ThemeContext.Provider value={THEMES[themeId]}>
      <AppShell themeId={themeId} setThemeId={setThemeId} />
    </ThemeContext.Provider>
  )
}
