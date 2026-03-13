import { useState, useEffect, useCallback } from 'react'
import { ThemeContext, THEMES, useTheme } from './components/shared.jsx'
import TabResumen       from './tabs/TabResumen.jsx'
import TabTopProductos  from './tabs/TabTopProductos.jsx'
import TabInventario    from './tabs/TabInventario.jsx'
import TabHistorial     from './tabs/TabHistorial.jsx'
import TabCaja          from './tabs/TabCaja.jsx'
import TabGastos        from './tabs/TabGastos.jsx'
import TabCompras       from './tabs/TabCompras.jsx'
import TabCatalogo      from './tabs/TabCatalogo.jsx'
import TabKardex        from './tabs/TabKardex.jsx'
import TabResultados    from './tabs/TabResultados.jsx'
import TabVentasRapidas from './tabs/TabVentasRapidas.jsx'
// ── LOGO SVG ─────────────────────────────────────────────────────────────────
function LogoSVG({ height = 38, dark = false }) {
  const textColor   = dark ? '#e2e8f0' : '#1a1410'
  const accentColor = dark ? '#ff5555' : '#b81a10'
  return (
    <svg width={Math.round(152 * (height / 44))} height={height} viewBox="0 0 152 44" fill="none" xmlns="http://www.w3.org/2000/svg" style={{display:"block",flexShrink:0}}>
      {/* Badge rojo */}
      <circle cx="22" cy="22" r="21" fill={accentColor}/>
      <circle cx="22" cy="22" r="21" fill="url(#logoGrad)" opacity="0.3"/>
      <defs>
        <radialGradient id="logoGrad" cx="35%" cy="30%" r="70%">
          <stop offset="0%" stopColor="white" stopOpacity="0.4"/>
          <stop offset="100%" stopColor="black" stopOpacity="0.2"/>
        </radialGradient>
      </defs>
      {/* Llave inglesa */}
      <g transform="translate(22,22) rotate(-40)">
        <rect x="-2.5" y="-11" width="5" height="22" rx="2.5" fill="white"/>
        <rect x="-6"   y="-11" width="12" height="5.5" rx="2.5" fill="white"/>
        <rect x="-6"   y="5.5" width="12" height="5.5" rx="2.5" fill="white"/>
        <circle cx="0" cy="10" r="4.5" fill="white"/>
        <circle cx="0" cy="10" r="2"   fill={accentColor}/>
      </g>
      {/* Texto FERRETERÍA */}
      <text x="51" y="18"
        fontFamily="system-ui,-apple-system,sans-serif"
        fontSize="9" fontWeight="700" letterSpacing="2"
        fill={textColor} opacity="0.65">FERRETERÍA</text>
      {/* Texto PUNTO ROJO */}
      <text x="51" y="35"
        fontFamily="system-ui,-apple-system,sans-serif"
        fontSize="16" fontWeight="900" letterSpacing="-0.3"
        fill={accentColor}>PUNTO ROJO</text>
    </svg>
  )
}



const REFRESH_OPTIONS = [
  { label: 'Off', value: 0   },
  { label: '30s', value: 30  },
  { label: '1m',  value: 60  },
  { label: '5m',  value: 300 },
]

const TABS = ['Resumen','Ventas Rápidas','Top 10','Inventario','Historial',
              'Caja','Gastos','Compras','Catálogo','Kárdex','Resultados']
const TAB_ICONS = {
  'Resumen':'📊','Ventas Rápidas':'⚡','Top 10':'🏆','Inventario':'📦',
  'Historial':'🧾','Caja':'💰','Gastos':'💸','Compras':'🚚',
  'Catálogo':'🏷️','Kárdex':'📋','Resultados':'📈',
}

// Tabs fijos en la barra inferior
const BOTTOM_TABS = ['Ventas Rápidas','Resumen','Historial','Caja']

// ── Hook de detección móvil ───────────────────────────────────────────────────
function useIsMobile() {
  const [v, setV] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setV(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return v
}
// ── HEADER DESKTOP ───────────────────────────────────────────────────────────
function HeaderDesktop({ themeId, setThemeId, refreshInterval, setRefreshInterval,
                         lastRefresh, onRefresh, countdown }) {
  const t = useTheme()
  const isDark = themeId === 'dark' || themeId === 'mid'
  return (
    <div style={{
      borderBottom:`1px solid ${t.border}`,
      padding:'0 28px',
      display:'flex', alignItems:'center', justifyContent:'space-between',
      height:60, background:t.header, position:'sticky', top:0, zIndex:20,
      boxShadow: isDark ? '0 1px 0 rgba(255,255,255,.04), 0 4px 24px rgba(0,0,0,.4)' : '0 1px 0 rgba(0,0,0,.06), 0 4px 20px rgba(0,0,0,.06)',
      gap:12,
    }}>
      {/* Logo */}
      <div style={{ display:'flex', alignItems:'center', gap:16, flexShrink:0 }}>
        <LogoSVG height={38} dark={isDark}/>
        <div style={{ width:1, height:22, background:t.border, opacity:.7 }}/>
        <span style={{
          fontSize:9, color:t.textMuted, letterSpacing:'.18em',
          textTransform:'uppercase', fontWeight:600,
        }}>Dashboard</span>
      </div>

      {/* Controles */}
      <div style={{ display:'flex', alignItems:'center', gap:10 }}>
        {/* Hora y countdown */}
        {lastRefresh && (
          <div style={{
            display:'flex', alignItems:'center', gap:6,
            fontSize:11, color:t.textMuted,
            background:t.card, border:`1px solid ${t.border}`,
            borderRadius:8, padding:'4px 10px',
          }}>
            <span style={{opacity:.6}}>🕐</span>
            <span>{lastRefresh}</span>
            {refreshInterval > 0 && countdown > 0 && (
              <span style={{
                background:t.accent, color:'#fff',
                borderRadius:99, padding:'1px 7px', fontSize:9, fontWeight:700,
                marginLeft:2,
              }}>{countdown}s</span>
            )}
          </div>
        )}

        {/* Botón refresh */}
        <button onClick={onRefresh} title="Actualizar" style={{
          background:t.accentSub, border:`1.5px solid ${t.accent}55`,
          color:t.accent, borderRadius:8, width:34, height:34,
          fontSize:16, cursor:'pointer', display:'flex',
          alignItems:'center', justifyContent:'center',
          transition:'all .15s',
        }}>↺</button>

        {/* Auto-refresh */}
        <div style={{
          display:'flex', alignItems:'center', gap:4,
          background:t.card, border:`1px solid ${t.border}`,
          borderRadius:8, padding:'3px 8px 3px 10px',
        }}>
          <span style={{ fontSize:9, color:t.textMuted, fontWeight:600, letterSpacing:'.1em', marginRight:2 }}>AUTO</span>
          <div style={{ display:'flex', gap:2 }}>
            {REFRESH_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setRefreshInterval(opt.value)} style={{
                background: refreshInterval===opt.value ? t.accent : 'transparent',
                border:`1px solid ${refreshInterval===opt.value ? t.accent : 'transparent'}`,
                color: refreshInterval===opt.value ? '#fff' : t.textMuted,
                fontSize:10, padding:'3px 7px', borderRadius:5, cursor:'pointer',
                fontWeight: refreshInterval===opt.value ? 700 : 400,
                transition:'all .12s',
              }}>{opt.label}</button>
            ))}
          </div>
        </div>

        {/* Separador */}
        <div style={{ width:1, height:22, background:t.border, opacity:.7 }}/>

        {/* Temas */}
        <div style={{
          display:'flex', gap:2,
          background:t.card, border:`1px solid ${t.border}`,
          borderRadius:8, padding:3,
        }}>
          {Object.values(THEMES).map(th => (
            <button key={th.id} onClick={() => setThemeId(th.id)} title={th.label} style={{
              background: themeId===th.id ? t.accent : 'transparent',
              border:'none',
              color: themeId===th.id ? '#fff' : t.textMuted,
              fontSize:12, width:30, height:26, borderRadius:6, cursor:'pointer',
              transition:'all .12s', display:'flex', alignItems:'center', justifyContent:'center',
            }}>{th.label.split(' ')[0]}</button>
          ))}
        </div>

        {/* Separador */}
        <div style={{ width:1, height:22, background:t.border, opacity:.7 }}/>

        {/* Bot status */}
        <div style={{
          display:'flex', alignItems:'center', gap:6,
          fontSize:10, color:t.textMuted,
        }}>
          <span style={{ display:'inline-block', width:7, height:7, borderRadius:'50%', background:'#22c55e', boxShadow:'0 0 6px #22c55e88' }}/>
          <span>Bot activo</span>
          <span style={{opacity:.5}}>·</span>
          <span>{new Date().toLocaleDateString('es-CO',{weekday:'short',day:'numeric',month:'short'})}</span>
        </div>
      </div>
    </div>
  )
}

// ── HEADER MÓVIL ──────────────────────────────────────────────────────────────
function HeaderMobile({ themeId, setThemeId, onRefresh, activeTab }) {
  const t = useTheme()
  const isDark = themeId === 'dark' || themeId === 'mid'
  const tIds = Object.keys(THEMES)
  return (
    <div style={{
      borderBottom:`1px solid ${t.border}`, padding:'0 16px',
      display:'flex', alignItems:'center', justifyContent:'space-between',
      height:54, background:t.header, position:'sticky', top:0, zIndex:20,
      boxShadow: isDark ? '0 4px 20px rgba(0,0,0,.5)' : '0 2px 12px rgba(0,0,0,.07)',
    }}>
      <LogoSVG height={32} dark={isDark}/>
      <span style={{ fontSize:12, color:t.textMuted, fontWeight:600 }}>
        {TAB_ICONS[activeTab]} {activeTab}
      </span>
      <div style={{ display:'flex', gap:6 }}>
        <button onClick={onRefresh} style={{
          background:t.accentSub, border:`1.5px solid ${t.accent}55`,
          color:t.accent, borderRadius:8, width:34, height:34,
          fontSize:16, cursor:'pointer', display:'flex',
          alignItems:'center', justifyContent:'center',
        }}>↺</button>
        <button onClick={() => {
          const idx = tIds.indexOf(themeId)
          setThemeId(tIds[(idx+1) % tIds.length])
        }} style={{
          background:t.card, border:`1px solid ${t.border}`,
          color:t.textMuted, borderRadius:8, width:34, height:34,
          fontSize:14, cursor:'pointer', display:'flex',
          alignItems:'center', justifyContent:'center',
        }}>
          {THEMES[themeId]?.label.split(' ')[0] ?? '🎨'}
        </button>
      </div>
    </div>
  )
}


// ── TABS NAV DESKTOP ──────────────────────────────────────────────────────────
function TabsNavDesktop({ activeTab, setTab }) {
  const t = useTheme()
  return (
    <div style={{
      padding:'0 22px', display:'flex', gap:2,
      borderBottom:`1px solid ${t.border}`, background:t.header,
      position:'sticky', top:54, zIndex:19,
      overflowX:'auto',
    }}>
      <style>{`.dtabs::-webkit-scrollbar{display:none}`}</style>
      {TABS.map(tab => {
        const active = activeTab === tab
        return (
          <button key={tab} onClick={() => setTab(tab)} style={{
            background: active ? t.accentSub : 'transparent',
            border:'none', borderBottom:`2px solid ${active ? t.accent : 'transparent'}`,
            color: active ? t.accent : t.textMuted,
            fontSize:12, padding:'10px 16px', cursor:'pointer',
            fontWeight: active ? 600 : 400, borderRadius:'6px 6px 0 0',
            transition:'all .15s', whiteSpace:'nowrap',
            display:'flex', alignItems:'center', gap:6,
          }}>
            <span>{TAB_ICONS[tab]}</span><span>{tab}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── BOTTOM NAV MÓVIL ──────────────────────────────────────────────────────────
function BottomNav({ activeTab, setTab }) {
  const t = useTheme()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const otrosTabs = TABS.filter(x => !BOTTOM_TABS.includes(x))
  const estaEnOtros = !BOTTOM_TABS.includes(activeTab)

  return (
    <>
      {/* Barra fija inferior */}
      <div style={{
        position:'fixed', bottom:0, left:0, right:0, zIndex:100,
        background:t.header, borderTop:`1px solid ${t.border}`,
        display:'flex', height:60,
        boxShadow:'0 -4px 20px rgba(0,0,0,.25)',
      }}>
        {BOTTOM_TABS.map(tab => {
          const active = activeTab === tab
          return (
            <button key={tab} onClick={() => { setTab(tab); setDrawerOpen(false) }} style={{
              flex:1, background:'none', border:'none',
              display:'flex', flexDirection:'column', alignItems:'center',
              justifyContent:'center', gap:2, cursor:'pointer',
              color: active ? t.accent : t.textMuted,
              borderTop:`2px solid ${active ? t.accent : 'transparent'}`,
              transition:'all .15s',
            }}>
              <span style={{ fontSize:20 }}>{TAB_ICONS[tab]}</span>
              <span style={{ fontSize:9, fontWeight: active ? 700 : 400 }}>
                {tab === 'Ventas Rápidas' ? 'Ventas' : tab}
              </span>
            </button>
          )
        })}
        {/* Botón Más */}
        <button onClick={() => setDrawerOpen(v => !v)} style={{
          flex:1, background:'none', border:'none',
          display:'flex', flexDirection:'column', alignItems:'center',
          justifyContent:'center', gap:2, cursor:'pointer',
          color: estaEnOtros ? t.accent : t.textMuted,
          borderTop:`2px solid ${estaEnOtros ? t.accent : 'transparent'}`,
          transition:'all .15s',
        }}>
          <span style={{ fontSize:20 }}>{drawerOpen ? '✕' : '☰'}</span>
          <span style={{ fontSize:9, fontWeight: estaEnOtros ? 700 : 400 }}>
            {estaEnOtros ? activeTab.slice(0,6) : 'Más'}
          </span>
        </button>
      </div>

      {/* Drawer "Más" desde abajo */}
      {drawerOpen && (
        <div onClick={() => setDrawerOpen(false)} style={{
          position:'fixed', inset:0, background:'#00000077', zIndex:99,
          display:'flex', flexDirection:'column', justifyContent:'flex-end',
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background:t.card, borderRadius:'18px 18px 0 0',
            padding:'12px 0 70px',
            animation:'drawerUp .2s ease',
          }}>
            <style>{`@keyframes drawerUp{from{transform:translateY(100%)}to{transform:translateY(0)}}`}</style>
            <div style={{ display:'flex', justifyContent:'center', marginBottom:16 }}>
              <div style={{ width:36, height:4, borderRadius:99, background:t.border }} />
            </div>
            <div style={{
              display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:4, padding:'0 8px',
            }}>
              {otrosTabs.map(tab => {
                const active = activeTab === tab
                return (
                  <button key={tab} onClick={() => { setTab(tab); setDrawerOpen(false) }} style={{
                    background: active ? t.accentSub : 'none', border:'none',
                    display:'flex', flexDirection:'column', alignItems:'center',
                    gap:5, padding:'14px 6px', cursor:'pointer',
                    color: active ? t.accent : t.text, borderRadius:12,
                  }}>
                    <span style={{ fontSize:22 }}>{TAB_ICONS[tab]}</span>
                    <span style={{ fontSize:10, fontWeight: active ? 700 : 400, textAlign:'center' }}>{tab}</span>
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

// ── APP SHELL ─────────────────────────────────────────────────────────────────
function AppShell({ themeId, setThemeId }) {
  const t        = useTheme()
  const isMobile = useIsMobile()

  const [tab,             setTab]             = useState('Resumen')
  const [refreshInterval, setRefreshInterval] = useState(0)
  const [refreshKey,      setRefreshKey]      = useState(0)
  const [lastRefresh,     setLastRefresh]     = useState('')
  const [countdown,       setCountdown]       = useState(0)

  const stamp = () => new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit',second:'2-digit'})

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
      fontFamily:"'DM Sans','Geist',system-ui,sans-serif",
      background:t.bg, minHeight:'100vh', color:t.text, fontSize:13,
      transition:'background .3s, color .3s',
    }}>
      <style>{`
        *, *::before, *::after { box-sizing:border-box; margin:0; padding:0 }
        button { font-family:inherit }
        button:focus, input:focus { outline:none }
        input::placeholder { color:${t.textMuted}; opacity:1 }
        @keyframes spin  { to { transform:rotate(360deg) } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        ::-webkit-scrollbar       { width:4px; height:4px }
        ::-webkit-scrollbar-track { background:${t.bg} }
        ::-webkit-scrollbar-thumb { background:${t.accent}; border-radius:2px }
      `}</style>

      {isMobile ? (
        <HeaderMobile themeId={themeId} setThemeId={setThemeId} onRefresh={doRefresh} activeTab={tab} />
      ) : (
        <HeaderDesktop
          themeId={themeId} setThemeId={setThemeId}
          refreshInterval={refreshInterval} setRefreshInterval={setRefreshInterval}
          lastRefresh={lastRefresh} onRefresh={doRefresh} countdown={countdown}
        />
      )}

      {!isMobile && <TabsNavDesktop activeTab={tab} setTab={setTab} />}

      <div style={{
        padding: isMobile ? '14px 12px' : '20px 22px',
        maxWidth: isMobile ? '100%' : 1280,
        margin:'0 auto',
        paddingBottom: isMobile ? 76 : 20,
      }}>
        {tab==='Resumen'        && <TabResumen       refreshKey={refreshKey} />}
        {tab==='Ventas Rápidas' && <TabVentasRapidas refreshKey={refreshKey} />}
        {tab==='Top 10'         && <TabTopProductos  refreshKey={refreshKey} />}
        {tab==='Inventario'     && <TabInventario    refreshKey={refreshKey} />}
        {tab==='Historial'      && <TabHistorial     refreshKey={refreshKey} />}
        {tab==='Caja'           && <TabCaja          refreshKey={refreshKey} />}
        {tab==='Gastos'         && <TabGastos        refreshKey={refreshKey} />}
        {tab==='Compras'        && <TabCompras       refreshKey={refreshKey} />}
        {tab==='Catálogo'       && <TabCatalogo      refreshKey={refreshKey} />}
        {tab==='Kárdex'         && <TabKardex        refreshKey={refreshKey} />}
        {tab==='Resultados'     && <TabResultados    refreshKey={refreshKey} />}
      </div>

      {!isMobile && (
        <div style={{
          borderTop:`1px solid ${t.border}`, padding:'10px 22px', marginTop:20,
          display:'flex', justifyContent:'space-between',
        }}>
          <span style={{ fontSize:10, color:t.textMuted }}>Ferretería Punto Rojo · Dashboard v5</span>
          <span style={{ fontSize:10, color:t.textMuted }}>Google Sheets · Excel · memoria.json</span>
        </div>
      )}

      {isMobile && <BottomNav activeTab={tab} setTab={setTab} />}
    </div>
  )
}

export default function App() {
  const [themeId, setThemeId] = useState('concreto')
  return (
    <ThemeContext.Provider value={THEMES[themeId]}>
      <AppShell themeId={themeId} setThemeId={setThemeId} />
    </ThemeContext.Provider>
  )
}
