import React, { useState, useEffect, useCallback, useRef } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ThemeContext, THEMES, useTheme } from './components/shared.jsx'
import { ProtectedRoute } from './components/ProtectedRoute.jsx'
import { VendorProvider, useVendorFilter } from './hooks/useVendorFilter.jsx'
import { useAuth } from './hooks/useAuth'
import { useRealtime } from './hooks/useRealtime'
import Login from './pages/Login.jsx'
import TabResumen         from './tabs/TabResumen.jsx'
import TabTopProductos    from './tabs/TabTopProductos.jsx'
import TabInventario      from './tabs/TabInventario.jsx'
import TabHistorial       from './tabs/TabHistorial.jsx'
import TabCaja            from './tabs/TabCaja.jsx'
import TabGastos          from './tabs/TabGastos.jsx'
import TabCompras         from './tabs/TabCompras.jsx'
import TabComprasFiscal   from './tabs/TabComprasFiscal.jsx'
import TabKardex          from './tabs/TabKardex.jsx'
import TabResultados      from './tabs/TabResultados.jsx'
import TabVentasRapidas   from './tabs/TabVentasRapidas.jsx'
import TabHistoricoVentas from './tabs/TabHistoricoVentas.jsx'
import TabProveedores     from './tabs/TabProveedores.jsx'
import TabFacturacion     from './tabs/TabFacturacion.jsx'
import TabLibroIVA        from './tabs/TabLibroIVA.jsx'
import ChatWidget          from './components/ChatWidget.jsx'
import AnimatedBackground  from './components/ui/AnimatedBackground.jsx'

// ── Iconos SVG limpios (sin emojis) ──────────────────────────────────────────
function Icon({ name, size = 20, color = 'currentColor', strokeWidth = 1.75 }) {
  const paths = {
    'Resumen':        'M3 3v18h18M7 16l4-5 4 4 4-6',
    'Ventas Rápidas': 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
    'Top 10':         'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z',
    'Inventario':     'M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM16 3H8L6 7h12l-2-4z',
    'Historial':      'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4',
    'Caja':           'M2 9h20M2 9a2 2 0 012-2h16a2 2 0 012 2M2 9v9a2 2 0 002 2h16a2 2 0 002-2V9M12 14v3m0 0l-2-2m2 2l2-2',
    'Gastos':         'M17 7l-10 10M7 7h10v10',
    'Compras':        'M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v9a2 2 0 01-2 2h-2M14 22a2 2 0 100-4 2 2 0 000 4zM5 22a2 2 0 100-4 2 2 0 000 4z',
    'Kárdex':         'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
    'Resultados':     'M22 12h-4l-3 9L9 3l-3 9H2',
    'Histórico':      'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',
    'Proveedores':    'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4',
    'Facturación':    'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
    'Más':            'M4 6h16M4 12h16M4 18h16',
    'Cerrar':         'M6 18L18 6M6 6l12 12',
    'Refresh':        'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <path d={paths[name] || paths['Más']}/>
    </svg>
  )
}

// ── Logo SVG vectorial ────────────────────────────────────────────────────────
function Logo({ size = 40, themeId }) {
  const isDark = themeId !== 'caramelo'
  const red    = themeId === 'brasa' ? '#F03418' : themeId === 'ferrari' ? '#DA291C' : '#C8200E'
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

      <circle cx={cx} cy={cy} r={r} fill="url(#lgr)" filter="url(#shdw)"/>
      <circle cx={cx} cy={cy} r={r - 0.5}
        fill="none" stroke="rgba(255,255,255,.18)" strokeWidth="1.2"/>

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

      <text x={size + 10} y={h * 0.41}
        fontFamily="'Inter',Arial,Helvetica,sans-serif"
        fontSize={h * 0.225} fontWeight="500" letterSpacing="0.16em"
        fill={sub}>FERRETERÍA</text>

      <text x={size + 8} y={h * 0.82}
        fontFamily="'Inter',Arial,Helvetica,sans-serif"
        fontSize={h * 0.41} fontWeight="800" letterSpacing="-0.025em"
        fill={txt}>PUNTO ROJO</text>

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

const TAB_GROUPS = [
  { id: 'reportes',     label: 'Reportes',     icon: 'Resumen',        tabs: ['Resumen', 'Resultados', 'Top 10', 'Histórico'] },
  { id: 'ventas',       label: 'Ventas',       icon: 'Ventas Rápidas', tabs: ['Ventas Rápidas', 'Historial'] },
  { id: 'finanzas',     label: 'Finanzas',          icon: 'Caja',           tabs: ['Caja', 'Gastos', 'Kárdex'] },
  { id: 'almacen',      label: 'Almacén',           icon: 'Inventario',     tabs: ['Inventario', 'Compras', 'Proveedores'] },
  { id: 'contabilidad', label: 'Contabilidad Fiscal', icon: 'Libro IVA',   tabs: ['Facturación', 'Compras Fiscal', 'Libro IVA'] },
]
const TABS = TAB_GROUPS.flatMap(g => g.tabs)

function useIsMobile() {
  const getIsMobile = () => {
    if (typeof window === 'undefined') return false
    // Usar window.innerWidth, no screen — screen no se actualiza bien en todos los browsers al rotar
    return window.innerWidth < 768
  }
  const [v, setV] = useState(getIsMobile)
  useEffect(() => {
    const handler = () => {
      // Esperar 150ms después de rotate para que el DOM se estabilice
      setTimeout(() => setV(getIsMobile()), 150)
    }
    window.addEventListener('resize', handler)
    window.addEventListener('orientationchange', handler)
    return () => {
      window.removeEventListener('resize', handler)
      window.removeEventListener('orientationchange', handler)
    }
  }, [])
  return v
}

// ── Vendor Selector Helper ────────────────────────────────────────────────────
function HeaderVendorSelector() {
  const t = useTheme()
  const { isAdmin } = useAuth()
  const vendorCtx = useVendorFilter()
  const { vendedores, selectedVendor, setSelectedVendor } = vendorCtx || {}

  if (!isAdmin()) return null

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      background: t.card, border: `1px solid ${t.border}`,
      borderRadius: t.radius ?? 10, padding: '8px 12px',
    }}>
      <label style={{
        fontSize: 11, color: t.textMuted, fontWeight: 600,
        letterSpacing: '.12em', textTransform: 'uppercase',
      }}>Vendedor</label>
      <select
        value={selectedVendor || ''}
        onChange={(e) => {
          const val = parseInt(e.target.value) || null
          console.log('[VendorSelector] selectedVendor:', val)
          setSelectedVendor(val)
        }}
        style={{
          background: t.card, border: `1px solid #C8200E66`,
          color: t.text, borderRadius: t.radius ?? 6, padding: '4px 8px',
          fontSize: 11, fontWeight: 500, cursor: 'pointer',
          outline: 'none',
        }}
      >
        <option value="">Todos los vendedores</option>
        {(vendedores || []).map(v => (
          <option key={v.id} value={v.id}>{v.nombre}</option>
        ))}
      </select>
    </div>
  )
}

// ── Header Desktop ────────────────────────────────────────────────────────────
function HeaderDesktop({ themeId, setThemeId, refreshInterval, setRefreshInterval,
                         lastRefresh, onRefresh, countdown }) {
  const t      = useTheme()
  const isDark = themeId !== 'caramelo'
  return (
    <header style={{
      background: t.header,
      backdropFilter: t.headerBlur,
      WebkitBackdropFilter: t.headerBlur,
      borderBottom: `1px solid ${t.border}`,
      position: 'sticky', top: 0, zIndex: 30,
      boxShadow: themeId === 'ferrari' ? 'none' : isDark
        ? '0 1px 0 rgba(255,255,255,.04), 0 8px 32px rgba(0,0,0,.40)'
        : '0 1px 0 rgba(0,0,0,.04), 0 4px 20px rgba(0,0,0,.06)',
    }}>
      <div style={{
        maxWidth: 1400, margin: '0 auto', padding: '0 28px',
        height: 66, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', gap: 16,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap: 12, flexShrink: 0 }}>
          <Logo size={40} themeId={themeId}/>
          <span style={{
            fontSize: 9, fontWeight: 800, letterSpacing: '.18em',
            color: t.accent, background: t.accentSub,
            border: `1px solid ${t.accent}30`,
            borderRadius: t.radius ?? 99, padding: '3px 9px', textTransform: 'uppercase',
          }}>v5</span>
        </div>

        <div style={{ display:'flex', alignItems:'center', gap: 8 }}>
          {lastRefresh && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: t.card, border: `1px solid ${t.border}`,
              borderRadius: t.radius ?? 10, padding: '6px 12px',
              fontSize: 11, color: t.textSub, fontWeight: 500,
            }}>
              <span style={{ fontSize: 13, opacity: .7 }}>🕐</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{lastRefresh}</span>
              {refreshInterval > 0 && countdown > 0 && (
                <span style={{
                  background: t.accent, color: '#fff',
                  borderRadius: t.radius ?? 99, padding: '1px 7px', fontSize: 9,
                  fontWeight: 800, marginLeft: 2,
                }}>{countdown}s</span>
              )}
            </div>
          )}

          <button onClick={onRefresh} title="Actualizar" style={{
            background: t.accentSub, border: `1.5px solid ${t.accent}40`,
            color: t.accent, borderRadius: t.radius ?? 10, width: 38, height: 38,
            cursor: 'pointer', display: 'flex',
            alignItems: 'center', justifyContent: 'center', transition: 'all .15s',
          }}>
            <Icon name="Refresh" size={16} color={t.accent} strokeWidth={2}/>
          </button>

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: t.radius ?? 10, padding: '5px 10px',
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
                  padding: '3px 9px', borderRadius: t.radius ?? 99, cursor: 'pointer',
                  transition: 'all .13s',
                }}>{opt.label}</button>
              )
            })}
          </div>

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          <div style={{
            display: 'flex', gap: 2,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: t.radius ?? 10, padding: 4,
          }}>
            {Object.values(THEMES).map(th => {
              const cur = themeId === th.id
              return (
                <button key={th.id} onClick={() => setThemeId(th.id)}
                  title={th.label} style={{
                    background: cur ? t.accent : 'transparent',
                    border: 'none', borderRadius: t.radius ?? 7,
                    color: cur ? '#fff' : t.textMuted,
                    width: 32, height: 28, fontSize: 14, cursor: 'pointer',
                    transition: 'all .13s',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>{th.label.split(' ')[0]}</button>
              )
            })}
          </div>

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          {HeaderVendorSelector()}

          <div style={{ width:1, height:22, background:t.border, opacity:.5, margin:'0 2px' }}/>

          <div style={{
            display: 'flex', alignItems: 'center', gap: 7,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: t.radius ?? 10, padding: '6px 12px',
            fontSize: 11, color: t.textSub,
          }}>
            <span style={{
              display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
              background: '#34D060',
              boxShadow: themeId === 'ferrari' ? 'none' : '0 0 0 2px rgba(52,208,96,.18), 0 0 8px rgba(52,208,96,.5)',
              animation: 'pulse 2.5s ease infinite',
            }}/>
            <span style={{ fontWeight: 600 }}>Bot activo</span>
            <span style={{ opacity: .3 }}>·</span>
            <span style={{ color: t.textMuted }}>
              {new Date().toLocaleDateString('es-CO', { weekday:'short', day:'numeric', month:'short' })}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}

// ── Header Móvil ─────────────────────────────────────────────────────────────
function HeaderMobile({ themeId, setThemeId, onRefresh, activeTab }) {
  const t    = useTheme()
  const tIds = Object.keys(THEMES)
  return (
    <header style={{
      background: t.header,
      backdropFilter: t.headerBlur,
      WebkitBackdropFilter: t.headerBlur,
      borderBottom: `1px solid ${t.border}`,
      position: 'sticky', top: 0, zIndex: 30,
      height: 'calc(58px + env(safe-area-inset-top, 0px))',
      paddingTop: 'env(safe-area-inset-top, 0px)',
      boxShadow: themeId === 'ferrari' ? 'none' : themeId !== 'caramelo'
        ? '0 4px 24px rgba(0,0,0,.45)'
        : '0 2px 12px rgba(0,0,0,.06)',
    }}>
      <div style={{ height: 58, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px' }}>
      <Logo size={32} themeId={themeId}/>

      {/* Tab activo centrado */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        background: t.accentSub,
        border: `1px solid ${t.accent}25`,
        borderRadius: t.radius ?? 99,
        padding: '5px 12px',
      }}>
        <Icon name={activeTab} size={13} color={t.accent} strokeWidth={2.2}/>
        <span style={{ fontSize: 11, color: t.accent, fontWeight: 700, letterSpacing: '.02em' }}>
          {activeTab === 'Ventas Rápidas' ? 'Ventas' : activeTab}
        </span>
      </div>

      <div style={{ display:'flex', gap: 6 }}>
        <button onClick={onRefresh} style={{
          background: t.accentSub, border: `1.5px solid ${t.accent}40`,
          color: t.accent, borderRadius: t.radius ?? 10, width: 36, height: 36,
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="Refresh" size={15} color={t.accent} strokeWidth={2.2}/>
        </button>
        <button onClick={() => {
          const i = tIds.indexOf(themeId)
          setThemeId(tIds[(i + 1) % tIds.length])
        }} style={{
          background: t.card, border: `1px solid ${t.border}`,
          color: t.textMuted, borderRadius: t.radius ?? 10, width: 36, height: 36,
          fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{THEMES[themeId]?.label.split(' ')[0] ?? '🎨'}</button>
      </div>
      </div>
    </header>
  )
}

// ── Tabs Nav Desktop — grupos + sub-tabs ──────────────────────────────────────
function TabsNavDesktop({ activeTab, setTab }) {
  const t = useTheme()
  const [hoveredGroup, setHoveredGroup] = useState(null)
  const [hoveredTab,   setHoveredTab]   = useState(null)
  const activeGroup = TAB_GROUPS.find(g => g.tabs.includes(activeTab)) || TAB_GROUPS[0]
  const subTabs     = activeGroup.tabs

  return (
    <nav style={{
      background: t.header,
      backdropFilter: t.headerBlur,
      WebkitBackdropFilter: t.headerBlur,
      borderBottom: `1px solid ${t.border}`,
      position: 'sticky', top: 66, zIndex: 20,
    }}>
      {/* Fila 1 — Grupos */}
      <div style={{
        maxWidth: 1400, margin: '0 auto', padding: '0 20px',
        display: 'flex', gap: 2, alignItems: 'center',
        borderBottom: subTabs.length > 1 ? `1px solid ${t.border}40` : 'none',
      }}>
        {TAB_GROUPS.map(group => {
          const isActive  = group.id === activeGroup.id
          const isHovered = hoveredGroup === group.id && !isActive
          return (
            <button
              key={group.id}
              onClick={() => setTab(group.tabs[0])}
              onMouseEnter={() => setHoveredGroup(group.id)}
              onMouseLeave={() => setHoveredGroup(null)}
              style={{
                position: 'relative', cursor: 'pointer', whiteSpace: 'nowrap',
                display: 'flex', alignItems: 'center', gap: 7,
                border: 'none',
                background: t.id === 'ferrari'
                  ? 'transparent'
                  : isActive ? t.accentSub : isHovered ? `${t.accentSub}50` : 'transparent',
                color: isActive ? t.accent : isHovered ? t.textSub : t.textMuted,
                fontSize: 12, fontWeight: isActive ? 700 : 500,
                padding: t.id === 'ferrari' ? '10px 14px 8px' : '8px 14px',
                borderRadius: t.id === 'ferrari' ? 0 : t.radius ?? 8,
                margin: t.id === 'ferrari' ? '0' : '5px 0',
                borderBottom: t.id === 'ferrari'
                  ? isActive ? `2px solid ${t.accent}` : '2px solid transparent'
                  : 'none',
                transition: 'color .15s, background .15s, border-color .15s',
                boxShadow: t.id === 'ferrari' ? 'none' : isActive ? `inset 0 0 0 1px ${t.accent}25` : 'none',
              }}
            >
              <Icon name={group.icon} size={13} color={isActive ? t.accent : isHovered ? t.textSub : t.textMuted} strokeWidth={isActive ? 2.2 : 1.75}/>
              <span>{group.label}</span>
              {group.tabs.length > 1 && t.id !== 'ferrari' && (
                <span style={{
                  fontSize: 9, fontWeight: 600,
                  color: isActive ? t.accent : t.textMuted,
                  background: isActive ? `${t.accent}18` : `${t.textMuted}15`,
                  borderRadius: t.radius ?? 99, padding: '1px 5px',
                  minWidth: 16, textAlign: 'center',
                }}>{group.tabs.length}</span>
              )}
            </button>
          )
        })}
      </div>

      {/* Fila 2 — Sub-tabs del grupo activo (solo si tiene más de 1) */}
      {subTabs.length > 1 && (
        <div style={{
          maxWidth: 1400, margin: '0 auto', padding: '0 28px',
          display: 'flex', gap: 2, alignItems: 'center',
        }}>
          {subTabs.map(tab => {
            const active  = activeTab === tab
            const hovered = hoveredTab === tab && !active
            return (
              <button
                key={tab}
                onClick={() => setTab(tab)}
                onMouseEnter={() => setHoveredTab(tab)}
                onMouseLeave={() => setHoveredTab(null)}
                style={{
                  border: 'none',
                  background: active ? `${t.accent}15` : hovered ? `${t.accent}08` : 'transparent',
                  color: active ? t.accent : hovered ? t.textSub : t.textMuted,
                  fontSize: 11, fontWeight: active ? 700 : 400,
                  padding: '5px 11px', cursor: 'pointer', whiteSpace: 'nowrap',
                  display: 'flex', alignItems: 'center', gap: 6,
                  borderRadius: t.id === 'ferrari' ? 0 : t.radius ?? 6,
                  margin: t.id === 'ferrari' ? '0' : '4px 0',
                  transition: 'color .15s, background .15s, border-color .15s',
                  borderBottom: active ? `2px solid ${t.accent}` : '2px solid transparent',
                  paddingBottom: t.id === 'ferrari' ? '7px' : '5px',
                }}
              >
                <Icon name={tab} size={12} color={active ? t.accent : hovered ? t.textSub : t.textMuted} strokeWidth={active ? 2.2 : 1.75}/>
                <span>{tab}</span>
              </button>
            )
          })}
        </div>
      )}
    </nav>
  )
}

// ── Bottom Nav Móvil — grupos con drawer de sub-tabs ─────────────────────────
function BottomNav({ activeTab, setTab }) {
  const t = useTheme()
  const [openGroup, setOpenGroup] = useState(null)
  const activeGroup = TAB_GROUPS.find(g => g.tabs.includes(activeTab)) || TAB_GROUPS[0]

  function handleGroupPress(group) {
    if (group.tabs.length === 1) {
      setTab(group.tabs[0])
      setOpenGroup(null)
    } else if (openGroup === group.id) {
      setOpenGroup(null)
    } else {
      setOpenGroup(group.id)
    }
  }

  const drawerGroup = TAB_GROUPS.find(g => g.id === openGroup)

  return (
    <>
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100,
        background: t.header,
        backdropFilter: t.headerBlur,
        WebkitBackdropFilter: t.headerBlur,
        borderTop: `1px solid ${t.border}`,
        display: 'flex',
        height: 'calc(64px + env(safe-area-inset-bottom, 0px))',
        boxShadow: '0 -8px 32px rgba(0,0,0,.18)',
        padding: '0 8px',
        paddingBottom: 'env(safe-area-inset-bottom, 0px)',
        alignItems: 'center',
        gap: 4,
      }}>
        {TAB_GROUPS.map(group => {
          const isActive  = group.id === activeGroup.id
          const isOpen    = openGroup === group.id
          return (
            <button key={group.id} onClick={() => handleGroupPress(group)} style={{
              flex: 1, background: 'none', border: 'none',
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', gap: 4, cursor: 'pointer',
              padding: '8px 2px', borderRadius: t.radius ?? 12, position: 'relative',
              transition: 'all .18s',
            }}>
              {(isActive || isOpen) && (
                <div style={{
                  position: 'absolute', top: 6, left: '50%',
                  transform: 'translateX(-50%)',
                  width: 36, height: 34,
                  background: isActive ? t.accentSub : `${t.textMuted}15`,
                  borderRadius: t.radius ?? 10,
                  border: `1px solid ${isActive ? t.accent + '25' : t.border}`,
                }}/>
              )}
              <span style={{ position: 'relative', zIndex: 1, display: 'flex' }}>
                <Icon name={group.icon} size={19} color={isActive ? t.accent : t.textMuted} strokeWidth={isActive ? 2.2 : 1.75}/>
              </span>
              <span style={{
                position: 'relative', zIndex: 1,
                fontSize: 9, fontWeight: isActive ? 700 : 500,
                color: isActive ? t.accent : t.textMuted,
                letterSpacing: '.01em', textAlign: 'center', lineHeight: 1.2,
              }}>{group.label}</span>
            </button>
          )
        })}
      </div>

      {/* Drawer sub-tabs del grupo */}
      {drawerGroup && drawerGroup.tabs.length > 1 && (
        <div onClick={() => setOpenGroup(null)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)',
          zIndex: 99, display: 'flex', flexDirection: 'column',
          justifyContent: 'flex-end', backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: t.card,
            borderRadius: `${t.radius ?? 20}px ${t.radius ?? 20}px 0 0`,
            padding: '20px 0',
            paddingBottom: 'calc(72px + env(safe-area-inset-bottom, 0px))',
            animation: 'drawerUp .2s cubic-bezier(.22,1,.36,1)',
            border: `1px solid ${t.border}`,
            borderBottom: 'none',
          }}>
            <style>{`@keyframes drawerUp{from{transform:translateY(100%)}to{transform:translateY(0)}}`}</style>
            <div style={{ display:'flex', justifyContent:'center', marginBottom: 16 }}>
              <div style={{ width: 36, height: 4, borderRadius: t.radius ?? 99, background: t.border }}/>
            </div>
            <div style={{ padding: '0 16px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon name={drawerGroup.icon} size={16} color={t.accent} strokeWidth={2}/>
              <span style={{ fontSize: 13, fontWeight: 700, color: t.text }}>{drawerGroup.label}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(drawerGroup.tabs.length, 4)},1fr)`, gap: 8, padding: '0 12px' }}>
              {drawerGroup.tabs.map(tab => {
                const active = activeTab === tab
                return (
                  <button key={tab} onClick={() => { setTab(tab); setOpenGroup(null) }} style={{
                    background: active ? t.accentSub : `${t.textMuted}08`,
                    border: active ? `1px solid ${t.accent}30` : `1px solid ${t.border}`,
                    display: 'flex', flexDirection: 'column', alignItems: 'center',
                    gap: 8, padding: '16px 6px', cursor: 'pointer',
                    color: active ? t.accent : t.text,
                    borderRadius: t.radius ?? 14, transition: 'all .15s',
                  }}>
                    <Icon name={tab} size={22} color={active ? t.accent : t.textMuted} strokeWidth={active ? 2.2 : 1.75}/>
                    <span style={{ fontSize: 11, fontWeight: active ? 700 : 500, textAlign: 'center', lineHeight: 1.2 }}>{tab}</span>
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

// ── Footer ────────────────────────────────────────────────────────────────────
function Footer() {
  const t = useTheme()
  const isFerrari = t.id === 'ferrari'
  return (
    <footer style={{
      borderTop: `1px solid ${isFerrari ? '#303030' : t.border}`,
      background: isFerrari ? '#303030' : 'transparent',
      padding: '14px 28px', marginTop: 24,
      maxWidth: isFerrari ? '100%' : 1400,
      margin: isFerrari ? '24px 0 0' : '24px auto 0',
      width: '100%',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    }}>
      <span style={{
        fontSize: 10,
        color: isFerrari ? '#8F8F8F' : t.textMuted,
        fontWeight: isFerrari ? 400 : 600,
        letterSpacing: isFerrari ? '.1em' : '.04em',
        textTransform: isFerrari ? 'uppercase' : 'none',
      }}>
        Ferretería Punto Rojo · Dashboard v5
      </span>
      <div style={{ display:'flex', alignItems:'center', gap: 7 }}>
        <span style={{
          display:'inline-block', width: 6, height: 6, borderRadius: '50%',
          background: '#34D060',
          boxShadow: isFerrari ? 'none' : '0 0 6px rgba(52,208,96,.5)',
        }}/>
        <span style={{ fontSize: 10, color: isFerrari ? '#8F8F8F' : t.textMuted }}>
          PostgreSQL · Railway
        </span>
      </div>
    </footer>
  )
}

// ── App Shell ─────────────────────────────────────────────────────────────────
function AppShell({ themeId, setThemeId, refreshRef }) {
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

  useEffect(() => {
    if (refreshRef) refreshRef.current = doRefresh
  }, [doRefresh, refreshRef])

  useEffect(() => { setLastRefresh(stamp()) }, [])

  // ── Tiempo real via SSE ────────────────────────────────────────────────────
  // El servidor notifica al dashboard cada vez que hay una venta, cambio de
  // inventario, cierre de caja, etc. — sin necesidad de polling constante.
  const EVENTOS_REFRESH = [
    'venta_registrada', 'venta_editada', 'venta_eliminada',
    'caja_abierta', 'caja_cerrada',
    'gasto_registrado',
    'compra_registrada', 'compra_actualizada',
    'inventario_actualizado',
  ]
  useRealtime((type) => {
    if (EVENTOS_REFRESH.includes(type)) {
      setRefreshKey(k => k + 1)
      setLastRefresh(stamp())
    }
  })

  // ── Fallback: intervalo manual si el usuario lo configura ────────────────
  // Con SSE activo este timer es solo un respaldo de seguridad.
  // refreshInterval === 0 → sin fallback (recomendado con SSE).
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

  useEffect(() => {
    if (!isMobile) return
    const lock = async () => {
      try { await screen.orientation.lock('portrait') } catch {}
    }
    lock()
    return () => { try { screen.orientation.unlock() } catch {} }
  }, [isMobile])

  return (
    <div style={{
      fontFamily: "'Inter', Arial, Helvetica, sans-serif",
      background: t.id === 'caramelo' ? 'transparent' : t.bgPattern,
      minHeight: '100dvh',
      color: t.text,
      fontSize: 14,
      transition: 'background .3s, color .25s',
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        ${t.id === 'caramelo' ? 'html,body{background:#F8F5F1}' : ''}
        *, *::before, *::after { box-sizing:border-box; margin:0; padding:0 }
        html { -webkit-text-size-adjust: 100% }
        button { font-family:inherit; cursor:pointer }
        button:focus, input:focus { outline:none }
        input::placeholder { color:${t.textMuted}; opacity:1 }
        @keyframes spin    { to { transform:rotate(360deg) } }
        @keyframes pulse   { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.6;transform:scale(.88)} }
        @keyframes fadeIn  { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
        @keyframes slideIn { from{opacity:0;transform:translateX(-6px)} to{opacity:1;transform:translateX(0)} }
        ::-webkit-scrollbar       { width:3px; height:3px }
        ::-webkit-scrollbar-track { background:transparent }
        ::-webkit-scrollbar-thumb { background:${t.accent}50; border-radius:99px }
        nav div::-webkit-scrollbar { display:none }
        .tab-content { animation:fadeIn .22s ease forwards }
        @media screen and (orientation: landscape) and (max-device-width: 900px) {
          .landscape-block { display: flex !important; }
        }
        * { -webkit-tap-highlight-color: transparent }
      `}</style>

      <AnimatedBackground />

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
        paddingBottom: isMobile ? 'calc(72px + env(safe-area-inset-bottom, 0px) + 16px)' : 24,
        position: 'relative',
      }}>
        {/* Ventas Rápidas — siempre montado para preservar el carrito entre tabs */}
        <div className={tab==='Ventas Rápidas' ? 'tab-content' : undefined}
             style={{ display: tab==='Ventas Rápidas' ? 'block' : 'none' }}>
          <TabVentasRapidas refreshKey={refreshKey}/>
        </div>

        {/* Resto de tabs — se montan/desmontan normalmente con animación */}
        {tab !== 'Ventas Rápidas' && (
          <div className="tab-content" key={tab}>
            {tab==='Resumen'          && <TabResumen         refreshKey={refreshKey}/>}
            {tab==='Top 10'           && <TabTopProductos    refreshKey={refreshKey}/>}
            {tab==='Inventario'       && <TabInventario      refreshKey={refreshKey}/>}
            {tab==='Historial'        && <TabHistorial       refreshKey={refreshKey}/>}
            {tab==='Caja'             && <TabCaja            refreshKey={refreshKey}/>}
            {tab==='Gastos'           && <TabGastos          refreshKey={refreshKey}/>}
            {tab==='Compras'          && <TabCompras         refreshKey={refreshKey}/>}
            {tab==='Compras Fiscal'   && <TabComprasFiscal   refreshKey={refreshKey}/>}
            {tab==='Kárdex'           && <TabKardex          refreshKey={refreshKey}/>}
            {tab==='Resultados'       && <TabResultados      refreshKey={refreshKey}/>}
            {tab==='Histórico'        && <TabHistoricoVentas refreshKey={refreshKey}/>}
            {tab==='Proveedores'      && <TabProveedores     refreshKey={refreshKey}/>}
            {tab==='Facturación'      && <TabFacturacion     refreshKey={refreshKey}/>}
            {tab==='Libro IVA'        && <TabLibroIVA        refreshKey={refreshKey}/>}
          </div>
        )}
      </main>

      {!isMobile && <Footer/>}
      {isMobile  && <BottomNav activeTab={tab} setTab={setTab}/>}

      {/* Bloqueo visual landscape */}
      {isMobile && (
        <div className="landscape-block" style={{
          display: 'none',
          position: 'fixed', inset: 0, zIndex: 99999,
          background: '#0A0A0A',
          flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 16,
          color: '#fff', textAlign: 'center', padding: 32,
        }}>
          <span style={{ fontSize: 52 }}>🔄</span>
          <span style={{ fontSize: 17, fontWeight: 700 }}>Girá el celular</span>
          <span style={{ fontSize: 13, opacity: .6, maxWidth: 240 }}>
            Esta app está diseñada para usarse en vertical
          </span>
        </div>
      )}

      <ChatWidget activeTab={tab} onRefresh={doRefresh}/>
    </div>
  )
}

// ── Error Boundary ────────────────────────────────────────────────────────────
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      const msg = this.state.error?.message || String(this.state.error)
      return (
        <div style={{
          minHeight: '100vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          background: '#FDF6EE', padding: 32, fontFamily: 'system-ui, sans-serif',
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, padding: 32, maxWidth: 560,
            boxShadow: '0 4px 24px rgba(0,0,0,0.10)', border: '1px solid #F5C6C2',
          }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
            <h2 style={{ color: '#C8200E', margin: '0 0 8px', fontSize: 18 }}>
              Error al cargar el dashboard
            </h2>
            <pre style={{
              background: '#FFF0EE', borderRadius: 8, padding: 12,
              fontSize: 12, color: '#7A2A20', overflowX: 'auto', whiteSpace: 'pre-wrap',
              wordBreak: 'break-word', margin: '0 0 16px',
            }}>{msg}</pre>
            <button
              onClick={() => window.location.reload()}
              style={{
                background: '#C8200E', color: '#fff', border: 'none',
                borderRadius: 8, padding: '8px 20px', cursor: 'pointer', fontSize: 14,
              }}
            >
              Recargar
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function Dashboard({ themeId, setThemeId, refreshRef }) {
  const { isAdmin } = useAuth()
  const content = (
    <ThemeContext.Provider value={THEMES[themeId]}>
      <AppShell themeId={themeId} setThemeId={setThemeId} refreshRef={refreshRef}/>
    </ThemeContext.Provider>
  )

  if (isAdmin()) {
    return <VendorProvider>{content}</VendorProvider>
  }
  return content
}

export default function App() {
  const [themeId, setThemeId] = useState(
    () => localStorage.getItem('ferrebot_theme') || 'caramelo'
  )
  const refreshRef = useRef(null)

  function handleSetThemeId(id) {
    setThemeId(id)
    localStorage.setItem('ferrebot_theme', id)
  }

  return (
    <ErrorBoundary>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Dashboard themeId={themeId} setThemeId={handleSetThemeId} refreshRef={refreshRef}/>
              </ProtectedRoute>
            }
          />
        </Routes>
      </Router>
    </ErrorBoundary>
  )
}
