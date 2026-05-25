/*
 * AppShell — layout principal: sidebar (desktop) o bottom-nav (móvil) + outlet.
 * Tema light/dark vía data-theme en <html>. Persiste en localStorage.
 */
import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { findRoute } from '@/routes.jsx'
import { useIsMobile } from './shared.jsx'
import { VendorProvider } from '../hooks/useVendorFilter.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useRealtime } from '../hooks/useRealtime.js'
import Sidebar from './Sidebar.jsx'
import MobileNav from './MobileNav.jsx'
import CommandPalette from './CommandPalette.jsx'
import ChatWidget from './ChatWidget.jsx'
import HeaderBar from './HeaderBar.jsx'

const EVENTOS_REFRESH = [
  'venta_registrada', 'venta_editada', 'venta_eliminada',
  'caja_abierta', 'caja_cerrada',
  'gasto_registrado',
  'compra_registrada', 'compra_actualizada',
  'inventario_actualizado',
]

function loadColorScheme() {
  try {
    const v = localStorage.getItem('ferrebot_color_scheme')
    if (v === 'light' || v === 'dark') return v
  } catch {}
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

function ShellInner() {
  const { isAdmin } = useAuth()
  const isMobile = useIsMobile()

  // ── Tema (light/dark via data-theme en <html>) ──────────────────────────────
  const [colorScheme, setColorScheme] = useState(loadColorScheme)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', colorScheme)
    try { localStorage.setItem('ferrebot_color_scheme', colorScheme) } catch {}
  }, [colorScheme])

  const toggleColorScheme = () => setColorScheme(s => s === 'dark' ? 'light' : 'dark')

  // ── Sidebar colapsado ───────────────────────────────────────────────────────
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('ferrebot_sidebar_collapsed') === '1' } catch { return false }
  })
  useEffect(() => {
    try { localStorage.setItem('ferrebot_sidebar_collapsed', collapsed ? '1' : '0') } catch {}
  }, [collapsed])

  // ── Refresh global (SSE + manual) ───────────────────────────────────────────
  const [refreshKey, setRefreshKey] = useState(0)
  const [lastRefresh, setLastRefresh] = useState('')

  const doRefresh = useCallback(() => {
    setRefreshKey(k => k + 1)
    setLastRefresh(new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
  }, [])

  useEffect(() => { doRefresh() }, [doRefresh])

  useRealtime((type) => {
    if (EVENTOS_REFRESH.includes(type)) doRefresh()
  })

  // ── Command Palette ─────────────────────────────────────────────────────────
  const [cmdOpen, setCmdOpen] = useState(false)

  const location = useLocation()
  const activeRoute = findRoute(location.pathname)
  const activeTabName = activeRoute?.label || 'Hoy'

  return (
    <div className="min-h-dvh bg-background text-foreground flex">
        {!isMobile && (
          <Sidebar
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            onOpenCommand={() => setCmdOpen(true)}
            colorScheme={colorScheme}
            onToggleColorScheme={toggleColorScheme}
          />
        )}

        <div className="flex-1 min-w-0 flex flex-col">
          <HeaderBar
            isMobile={isMobile}
            onOpenCommand={() => setCmdOpen(true)}
            onRefresh={doRefresh}
            lastRefresh={lastRefresh}
            colorScheme={colorScheme}
            onToggleColorScheme={toggleColorScheme}
            refreshKey={refreshKey}
          />

          <main
            className="flex-1 px-4 md:px-6 py-5 md:py-6 mx-auto w-full"
            style={{
              maxWidth: 1400,
              paddingBottom: isMobile ? 'calc(80px + env(safe-area-inset-bottom))' : undefined,
            }}
          >
            <Outlet context={{ refreshKey }} />
          </main>
        </div>

        {isMobile && <MobileNav />}

        <CommandPalette open={cmdOpen} setOpen={setCmdOpen} onRefresh={doRefresh} />
        <ChatWidget onRefresh={doRefresh} activeTab={activeTabName} />
      </div>
  )
}

export default function AppShell() {
  const { isAdmin } = useAuth()
  if (isAdmin()) {
    return <VendorProvider><ShellInner /></VendorProvider>
  }
  return <ShellInner />
}
