import { useState, useEffect, useCallback } from 'react'
import { ThemeContext, THEMES, useTheme } from './components/shared.jsx'
import TabResumen       from './tabs/TabResumen.jsx'
import TabTopProductos  from './tabs/TabTopProductos.jsx'
import TabInventario    from './tabs/TabInventario.jsx'
import TabHistorial     from './tabs/TabHistorial.jsx'
import TabCaja          from './tabs/TabCaja.jsx'
import TabGastos        from './tabs/TabGastos.jsx'
import TabCompras       from './tabs/TabCompras.jsx'
import TabKardex        from './tabs/TabKardex.jsx'
import TabResultados    from './tabs/TabResultados.jsx'
import TabVentasRapidas from './tabs/TabVentasRapidas.jsx'

// Logo SVG vectorial
function Logo({ size = 40, themeId }) {
  const isDark = themeId !== 'caramelo'
  const red    = themeId === 'brasa' ? '#F03418' : '#D42010'
  const txt    = isDark ? '#F0E8DC' : '#1C1410'
  const sub    = isDark ? 'rgba(240,232,220,.42)' : 'rgba(28,20,16,.38)'
  const w      = Math.round(size * 4.6)
  const h      = size
  const cx     = size / 2
  const cy     = size / 2
  const r      = size / 2 - 1

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} fill="none"
         xmlns="http://www.w3.org/2000/svg" style={{ display:'block', flexShrink:0 }}>
      <defs>
        <linearGradient id="lgr" x1="20%" y1="10%" x2="80%" y2="90%">
          <stop offset="0%" stopColor={red} stopOpacity="1"/>
          <stop offset="100%" stopColor={isDark ? "#A01808" : "#9A1408"} stopOpacity="1"/>
        </linearGradient>
        <filter id="shdw">
          <feDropShadow dx="0" dy="2" stdDeviation="3"
            floodColor={red} floodOpacity={isDark ? "0.45" : "0.2"}/>
        </filter>
      </defs>

      {/* Círculo con gradiente */}
      <circle cx={cx} cy={cy} r={r} fill="url(#lgr)" filter="url(#shdw)"/>
      <circle cx={cx} cy={cy} r={r - 0.5}
        fill="none" stroke="rgba(255,255,255,.18)" strokeWidth="1.2"/>

      {/* Icono llave inglesa */}
      <g transform={`translate(${cx},${cy}) rotate(-40)`}>
        <rect x={-size*0.075} y={-size*0.48} width={size*0.15} height={size*0.54}
          rx={size*0.075} fill="white" opacity="0.96"/>
        <rect x={-size*0.2} y={-size*0.48} width={size*0.4} height={size*0.165}
          rx={size*0.082} fill="white" opacity="0.96"/>
        <rect x={-size*0.2} y={-size*0.1} width={size*0.4} height={size*0.165}
          rx={size*0.082} fill="white" opacity="0.96"/>
        <circle cx="0" cy={size*0.28} r={size*0.135} fill="white" opacity="0.96"/>
        <circle cx="0" cy={size*0.28} r={size*0.065}
          fill="none" stroke={red} strokeWidth="2" opacity="0.88"/>
      </g>

      {/* Texto superior FERRETERÍA */}
      <text x={size + 10} y={h * 0.41}
        fontFamily="'Sora',system-ui,sans-serif"
        fontSize={h * 0.225} fontWeight="500" letterSpacing="0.16em"
        fill={sub}
      >FERRETERÍA</text>

      {/* Texto principal PUNTO ROJO */}
      <text x={size + 8} y={h * 0.82}
        fontFamily="'Sora',system-ui,sans-serif"
        fontSize={h * 0.41} fontWeight="800" letterSpacing="-0.025em"
        fill={txt}
      >PUNTO ROJO</text>

      {/* Línea roja decorativa */}
      <rect x={size + 8} y={h * 0.875} width={size * 2.0} height={h * 0.06}
        rx={h * 0.03} fill={red} opacity="0.8"/>
    </svg>
  )
}

const REFRESH_OPTIONS = [
  { label: 'Off', value: 0   },
  { label: '30s', value: 30  },
  { label: '1m',  value: 60  },
  { label: '5m',  value: 300 },
]

const TABS = [
  'Resumen','Ventas Rápidas','Top 10','Inventario','Historial',
  'Caja','Gastos','Compras','Kárdex','Resultados',
]
const TAB_ICONS = {
  'Resumen':'📊','Ventas Rápidas':'⚡','Top 10':'🏆','Inventario':'📦',
  'Historial':'🧾','Caja':'💰','Gastos':'💸','Compras':'🚚',
  'Kárdex':'📋','Resultados':'📈',
}
const BOTTOM_TABS = ['Ventas Rápidas','Resumen','Historial','Caja']

function useIsMobile() {
  const [v, setV] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setV(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return v
}

// Header Desktop
function HeaderDesktop({ themeId, setThemeId, refreshInterval, setRefreshInterval,
                         lastRefresh, onRefresh, countdown }) {
  const t      = useTheme()
  const isDark = themeId !== 'caramelo'
  return (
    <header style={{
      background: t.header, borderBottom: `1px solid ${t.border}`,
      position: 'sticky', top: 0, zIndex: 30,
      boxShadow: isDark
        ? '0 1px 0 rgba(255,255,255,.03), 0 8px 32px rgba(0,0,0,.35)'
        : '0 1px 0 rgba(0,0,0,.05), 0 4px 20px rgba(0,0,0,.05)',
    }}>
      <div style={{
        maxWidth: 1400, margin: '0 auto', padding: '0 28px',
        height: 66, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', gap: 16,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap: 12, flexShrink: 0 }}>
          <Logo size={40} themeId={themeId}/>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '.15em',
            color: t.accent, background: t.accentSub,
            border: `1px solid ${t.accent}30`,
            borderRadius: 99, padding: '3px 9px', textTransform: 'uppercase',
          }}>v5</span>
        </div>

        <div style={{ display:'flex', alignItems:'center', gap: 8 }}>
          {lastRefresh && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: t.card, border: `1px solid ${t.border}`,
              borderRadius: 10, padding: '6px 12px',
              fontSize: 11, color: t.textSub, fontWeight: 500,
            }}>
              <span style={{ fontSize: 13, opacity: .8 }}>🕐</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{lastRefresh}</span>
              {refreshInterval > 0 && countdown > 0 && (
                <span style={{
                  background: t.accent, color: '#fff',
                  borderRadius: 99, padding: '1px 7px', fontSize: 9,
                  fontWeight: 800, marginLeft: 2,
                }}>{countdown}s</span>
              )}
            </div>
          )}

          <button onClick={onRefresh} title="Actualizar" style={{
            background: t.accentSub, border: `1.5px solid ${t.accent}44`,
            color: t.accent, borderRadius: 10, width: 38, height: 38,
            fontSize: 17, cursor: 'pointer', display: 'flex',
            alignItems: 'center', justifyContent: 'center', transition: 'all .15s',
          }}>↺</button>

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 10, padding: '5px 10px',
          }}>
            <span style={{
              fontSize: 9, color: t.textMuted, fontWeight: 700,
              letterSpacing: '.14em', textTransform: 'uppercase',
            }}>Auto</span>
            {REFRESH_OPTIONS.map(opt => {
              const active = refreshInterval === opt.value
              return (
                <button key={opt.value} onClick={() => setRefreshInterval(opt.value)} style={{
                  background: active ? t.accent : 'transparent',
                  border: `1px solid ${active ? t.accent : t.border}`,
                  color: active ? '#fff' : t.textMuted,
                  fontSize: 10, fontWeight: active ? 700 : 500,
                  padding: '3px 9px', borderRadius: 99, cursor: 'pointer',
                  transition: 'all .13s',
                }}>{opt.label}</button>
              )
            })}
          </div>

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          <div style={{
            display: 'flex', gap: 2,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 10, padding: 4,
          }}>
            {Object.values(THEMES).map(th => {
              const cur = themeId === th.id
              return (
                <button key={th.id} onClick={() => setThemeId(th.id)}
                  title={th.label} style={{
                    background: cur ? t.accent : 'transparent',
                    border: 'none', borderRadius: 7,
                    color: cur ? '#fff' : t.textMuted,
                    width: 32, height: 28, fontSize: 14, cursor: 'pointer',
                    transition: 'all .13s',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>{th.label.split(' ')[0]}</button>
              )
            })}
          </div>

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          <div style={{
            display: 'flex', alignItems: 'center', gap: 7,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 10, padding: '6px 12px',
            fontSize: 11, color: t.textSub,
          }}>
            <span style={{
              display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
              background: '#34D060',
              boxShadow: '0 0 0 2px rgba(52,208,96,.18), 0 0 8px rgba(52,208,96,.5)',
              animation: 'pulse 2.5s ease infinite',
            }}/>
            <span style={{ fontWeight: 600 }}>Bot activo</span>
            <span style={{ opacity: .35 }}>·</span>
            <span style={{ color: t.textMuted }}>
              {new Date().toLocaleDateString('es-CO', { weekday:'short', day:'numeric', month:'short' })}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}

// Header Móvil
function HeaderMobile({ themeId, setThemeId, onRefresh, activeTab }) {
  const t    = useTheme()
  const tIds = Object.keys(THEMES)
  return (
    <header style={{
      background: t.header, borderBottom: `1px solid ${t.border}`,
      position: 'sticky', top: 0, zIndex: 30, height: 58,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px',
      boxShadow: themeId !== 'caramelo' ? '0 4px 20px rgba(0,0,0,.4)' : '0 2px 12px rgba(0,0,0,.06)',
    }}>
      <Logo size={34} themeId={themeId}/>
      <span style={{ fontSize: 12, color: t.textMuted, fontWeight: 600, display:'flex', alignItems:'center', gap: 5 }}>
        {TAB_ICONS[activeTab]} {activeTab}
      </span>
      <div style={{ display:'flex', gap: 6 }}>
        <button onClick={onRefresh} style={{
          background: t.accentSub, border: `1.5px solid ${t.accent}44`,
          color: t.accent, borderRadius: 9, width: 36, height: 36,
          fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>↺</button>
        <button onClick={() => {
          const i = tIds.indexOf(themeId)
          setThemeId(tIds[(i + 1) % tIds.length])
        }} style={{
          background: t.card, border: `1px solid ${t.border}`,
          color: t.textMuted, borderRadius: 9, width: 36, height: 36,
          fontSize: 15, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{THEMES[themeId]?.label.split(' ')[0] ?? '🎨'}</button>
      </div>
    </header>
  )
}

// Tabs Desktop
function TabsNavDesktop({ activeTab, setTab }) {
  const t = useTheme()
  return (
    <nav style={{
      background: t.header, borderBottom: `1px solid ${t.border}`,
      position: 'sticky', top: 66, zIndex: 20,
    }}>
      <div style={{
        maxWidth: 1400, margin: '0 auto', padding: '0 20px',
        display: 'flex', overflowX: 'auto',
      }}>
        {TABS.map(tab => {
          const active = activeTab === tab
          return (
            <button key={tab} onClick={() => setTab(tab)} style={{
              position: 'relative', background: 'transparent', border: 'none',
              borderBottom: `2.5px solid ${active ? t.accent : 'transparent'}`,
              color: active ? t.accent : t.textMuted,
              fontSize: 12.5, fontWeight: active ? 700 : 450,
              padding: '12px 15px 10px', cursor: 'pointer', whiteSpace: 'nowrap',
              display: 'flex', alignItems: 'center', gap: 6,
              transition: 'color .15s, border-color .15s',
            }}>
              {active && (
                <span style={{
                  position: 'absolute', inset: '4px 4px 0',
                  background: t.accentSub, borderRadius: '8px 8px 0 0',
                  pointerEvents: 'none',
                }}/>
              )}
              <span style={{ position: 'relative', fontSize: 14 }}>{TAB_ICONS[tab]}</span>
              <span style={{ position: 'relative' }}>{tab}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

// Bottom Nav Móvil
function BottomNav({ activeTab, setTab }) {
  const t = useTheme()
  const [open, setOpen] = useState(false)
  const others     = TABS.filter(x => !BOTTOM_TABS.includes(x))
  const isInOthers = !BOTTOM_TABS.includes(activeTab)

  return (
    <>
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100,
        background: t.header, borderTop: `1px solid ${t.border}`,
        display: 'flex', height: 62,
        boxShadow: '0 -8px 32px rgba(0,0,0,.2)',
      }}>
        {BOTTOM_TABS.map(tab => {
          const active = activeTab === tab
          return (
            <button key={tab} onClick={() => { setTab(tab); setOpen(false) }} style={{
              flex: 1, background: 'none', border: 'none',
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', gap: 3, cursor: 'pointer',
              color: active ? t.accent : t.textMuted,
              borderTop: `2.5px solid ${active ? t.accent : 'transparent'}`,
              transition: 'all .15s',
            }}>
              <span style={{ fontSize: 21 }}>{TAB_ICONS[tab]}</span>
              <span style={{ fontSize: 9, fontWeight: active ? 700 : 400 }}>
                {tab === 'Ventas Rápidas' ? 'Ventas' : tab}
              </span>
            </button>
          )
        })}
        <button onClick={() => setOpen(v => !v)} style={{
          flex: 1, background: 'none', border: 'none',
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', gap: 3, cursor: 'pointer',
          color: isInOthers ? t.accent : t.textMuted,
          borderTop: `2.5px solid ${isInOthers ? t.accent : 'transparent'}`,
          transition: 'all .15s',
        }}>
          <span style={{ fontSize: 21 }}>{open ? '✕' : '☰'}</span>
          <span style={{ fontSize: 9, fontWeight: isInOthers ? 700 : 400 }}>
            {isInOthers ? activeTab.slice(0, 6) : 'Más'}
          </span>
        </button>
      </div>

      {open && (
        <div onClick={() => setOpen(false)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)',
          zIndex: 99, display: 'flex', flexDirection: 'column',
          justifyContent: 'flex-end', backdropFilter: 'blur(4px)',
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: t.card, borderRadius: '20px 20px 0 0',
            padding: '16px 0 72px',
            animation: 'drawerUp .22s cubic-bezier(.22,1,.36,1)',
          }}>
            <style>{`@keyframes drawerUp{from{transform:translateY(100%)}to{transform:translateY(0)}}`}</style>
            <div style={{ display:'flex', justifyContent:'center', marginBottom: 16 }}>
              <div style={{ width: 40, height: 4, borderRadius: 99, background: t.border }}/>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 4, padding: '0 12px' }}>
              {others.map(tab => {
                const active = activeTab === tab
                return (
                  <button key={tab} onClick={() => { setTab(tab); setOpen(false) }} style={{
                    background: active ? t.accentSub : 'none',
                    border: active ? `1px solid ${t.accent}30` : '1px solid transparent',
                    display: 'flex', flexDirection: 'column', alignItems: 'center',
                    gap: 6, padding: '14px 6px', cursor: 'pointer',
                    color: active ? t.accent : t.text, borderRadius: 14,
                  }}>
                    <span style={{ fontSize: 24 }}>{TAB_ICONS[tab]}</span>
                    <span style={{ fontSize: 10, fontWeight: active ? 700 : 400, textAlign: 'center' }}>{tab}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// Footer
function Footer() {
  const t = useTheme()
  return (
    <footer style={{
      borderTop: `1px solid ${t.border}`, padding: '12px 28px', marginTop: 24,
      maxWidth: 1400, margin: '24px auto 0', width: '100%',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    }}>
      <span style={{ fontSize: 10, color: t.textMuted, fontWeight: 500 }}>
        Ferretería Punto Rojo · Dashboard v5
      </span>
      <div style={{ display:'flex', alignItems:'center', gap: 7 }}>
        <span style={{
          display:'inline-block', width: 6, height: 6, borderRadius: '50%',
          background: '#34D060', boxShadow: '0 0 6px rgba(52,208,96,.5)',
        }}/>
        <span style={{ fontSize: 10, color: t.textMuted }}>
          Google Sheets · Excel · memoria.json
        </span>
      </div>
    </footer>
  )
}

// App Shell
function AppShell({ themeId, setThemeId }) {
  const t        = useTheme()
  const isMobile = useIsMobile()

  const [tab,             setTab]             = useState('Resumen')
  const [refreshInterval, setRefreshInterval] = useState(0)
  const [refreshKey,      setRefreshKey]      = useState(0)
  const [lastRefresh,     setLastRefresh]     = useState('')
  const [countdown,       setCountdown]       = useState(0)

  const stamp = () => new Date().toLocaleTimeString('es-CO', {hour:'2-digit',minute:'2-digit',second:'2-digit'})

  const doRefresh = useCallback(() => {
    setRefreshKey(k => k + 1)
    setLastRefresh(stamp())
    if (refreshInterval > 0) setCountdown(refreshInterval)
  }, [refreshInterval])

  useEffect(() => { setLastRefresh(stamp()) }, [])

  useEffect(() => {
    if (refreshInterval === 0) { setCountdown(0); return }
    setCountdown(refreshInterval)
    const tick = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { setRefreshKey(k => k+1); setLastRefresh(stamp()); return refreshInterval }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [refreshInterval])

  return (
    <div style={{
      fontFamily: "'Sora', system-ui, sans-serif",
      background: t.bg, minHeight: '100vh', color: t.text, fontSize: 13,
      transition: 'background .25s, color .25s',
    }}>
      <style>{`
        *, *::before, *::after { box-sizing:border-box; margin:0; padding:0 }
        button { font-family:inherit; cursor:pointer }
        button:focus, input:focus { outline:none }
        input::placeholder { color:${t.textMuted}; opacity:1 }
        @keyframes spin  { to { transform:rotate(360deg) } }
        @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.6;transform:scale(.88)} }
        @keyframes fadeIn { from{opacity:0} to{opacity:1} }
        ::-webkit-scrollbar       { width:3px; height:3px }
        ::-webkit-scrollbar-track { background:transparent }
        ::-webkit-scrollbar-thumb { background:${t.accent}55; border-radius:99px }
        .tab-content { animation:fadeIn .2s ease forwards }
      `}</style>

      {isMobile ? (
        <HeaderMobile themeId={themeId} setThemeId={setThemeId} onRefresh={doRefresh} activeTab={tab}/>
      ) : (
        <HeaderDesktop
          themeId={themeId} setThemeId={setThemeId}
          refreshInterval={refreshInterval} setRefreshInterval={setRefreshInterval}
          lastRefresh={lastRefresh} onRefresh={doRefresh} countdown={countdown}
        />
      )}

      {!isMobile && <TabsNavDesktop activeTab={tab} setTab={setTab}/>}

      <main style={{
        maxWidth: isMobile ? '100%' : 1400, margin: '0 auto',
        padding: isMobile ? '14px 12px' : '24px 28px',
        paddingBottom: isMobile ? 76 : 24,
      }}>
        <div className="tab-content" key={tab}>
          {tab==='Resumen'        && <TabResumen       refreshKey={refreshKey}/>}
          {tab==='Ventas Rápidas' && <TabVentasRapidas refreshKey={refreshKey}/>}
          {tab==='Top 10'         && <TabTopProductos  refreshKey={refreshKey}/>}
          {tab==='Inventario'     && <TabInventario    refreshKey={refreshKey}/>}
          {tab==='Historial'      && <TabHistorial     refreshKey={refreshKey}/>}
          {tab==='Caja'           && <TabCaja          refreshKey={refreshKey}/>}
          {tab==='Gastos'         && <TabGastos        refreshKey={refreshKey}/>}
          {tab==='Compras'        && <TabCompras       refreshKey={refreshKey}/>}
          {tab==='Kárdex'         && <TabKardex        refreshKey={refreshKey}/>}
          {tab==='Resultados'     && <TabResultados    refreshKey={refreshKey}/>}
        </div>
      </main>

      {!isMobile && <Footer/>}
      {isMobile  && <BottomNav activeTab={tab} setTab={setTab}/>}
    </div>
  )
}

export default function App() {
  const [themeId, setThemeId] = useState('caramelo')
  return (
    <ThemeContext.Provider value={THEMES[themeId]}>
      <AppShell themeId={themeId} setThemeId={setThemeId}/>
    </ThemeContext.Provider>
  )
}
