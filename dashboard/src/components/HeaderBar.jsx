/*
 * HeaderBar — header sticky con título de ruta, refresh, vendor selector,
 * estado del bot y botón de búsqueda. Versión móvil compacta.
 */
import { useLocation, useNavigate } from 'react-router-dom'
import { Command, RefreshCw, Sun, Moon, Wallet } from 'lucide-react'
import { findRoute } from '@/routes.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'
import { useFetch, cop } from './shared.jsx'
import { cn } from '@/lib/utils'

export default function HeaderBar({ isMobile, onOpenCommand, onRefresh, lastRefresh, colorScheme, onToggleColorScheme, refreshKey = 0 }) {
  const location = useLocation()
  const route = findRoute(location.pathname)
  const title = route?.label || 'Hoy'

  return (
    <header className="sticky top-0 z-30 bg-surface/90 backdrop-blur-md border-b border-border">
      <div className="flex items-center gap-3 h-14 px-4 md:px-6">
        <h1 className="text-base md:text-lg font-semibold tracking-tight truncate">{title}</h1>

        <div className="flex-1" />

        <CajaStatusPill isMobile={isMobile} refreshKey={refreshKey} />

        {!isMobile && <VendorSelector />}

        {!isMobile && lastRefresh && (
          <span className="text-xs text-muted-foreground tabular hidden lg:inline">
            Actualizado {lastRefresh}
          </span>
        )}

        <button
          onClick={onRefresh}
          title="Refrescar"
          className="size-9 grid place-items-center rounded-md border border-border bg-surface text-muted-foreground hover:text-foreground hover:bg-surface-2 transition-colors"
        >
          <RefreshCw className="size-4" />
        </button>

        {isMobile && (
          <>
            <button
              onClick={onToggleColorScheme}
              title="Tema"
              className="size-9 grid place-items-center rounded-md border border-border bg-surface text-muted-foreground hover:text-foreground hover:bg-surface-2"
            >
              {colorScheme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
            <button
              onClick={onOpenCommand}
              title="Buscar"
              className="size-9 grid place-items-center rounded-md border border-border bg-surface text-muted-foreground hover:text-foreground hover:bg-surface-2"
            >
              <Command className="size-4" />
            </button>
          </>
        )}

        <div className="hidden md:flex items-center gap-2 px-3 h-9 rounded-md border border-border bg-surface text-xs">
          <span className="size-2 rounded-full bg-success animate-pulse" />
          <span className="text-muted-foreground">Bot activo</span>
        </div>
      </div>
    </header>
  )
}

function CajaStatusPill({ isMobile, refreshKey }) {
  const navigate = useNavigate()
  const { data: caja } = useFetch('/caja', [refreshKey])
  if (!caja) return null

  const abierta = !!caja.abierta
  const efectivoEsperado = caja.efectivo_esperado || 0

  return (
    <button
      type="button"
      onClick={() => navigate('/caja')}
      title={abierta ? `Caja abierta · esperado ${cop(efectivoEsperado)}` : 'Caja cerrada — abrir'}
      className={cn(
        'h-9 inline-flex items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors',
        abierta
          ? 'border-success/40 bg-success/10 text-success hover:bg-success/15'
          : 'border-border bg-surface text-muted-foreground hover:text-foreground hover:bg-surface-2',
      )}
    >
      <Wallet className="size-3.5" />
      {isMobile ? (
        <span className="font-semibold">{abierta ? 'Abierta' : 'Cerrada'}</span>
      ) : (
        <>
          <span className="font-semibold">{abierta ? 'Caja abierta' : 'Caja cerrada'}</span>
          {abierta && (
            <span className="hidden xl:inline tabular text-success/80">· {cop(efectivoEsperado)}</span>
          )}
        </>
      )}
    </button>
  )
}

function VendorSelector() {
  const { isAdmin } = useAuth()
  const ctx = useVendorFilter?.()
  if (!isAdmin() || !ctx) return null
  const { vendedores, selectedVendor, setSelectedVendor } = ctx
  return (
    <select
      value={selectedVendor || ''}
      onChange={(e) => setSelectedVendor(parseInt(e.target.value) || null)}
      className="text-xs h-9 px-2 rounded-md border border-border bg-surface text-foreground hover:bg-surface-2 transition-colors cursor-pointer"
    >
      <option value="">Todos los vendedores</option>
      {(vendedores || []).map(v => (
        <option key={v.id} value={v.id}>{v.nombre}</option>
      ))}
    </select>
  )
}
