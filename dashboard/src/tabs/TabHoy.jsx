/*
 * TabHoy — cockpit operativo, landing del dashboard.
 * Wireframe en `.planning/dashboard-redesign/IA.md` §Cockpit "HOY".
 * Bento minimalista: plata primero (ventas/caja/gastos), stock al final.
 * Datos derivados en cliente desde endpoints existentes — no toca backend.
 */
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, ArrowRight, Plus, AlertTriangle,
  ShoppingCart, Wallet, Receipt, Users, Package,
} from 'lucide-react'
import { useFetch, cop, num } from '@/components/shared.jsx'
import { useVendorFilter } from '@/hooks/useVendorFilter.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { cn } from '@/lib/utils'

export default function TabHoy({ refreshKey }) {
  const navigate = useNavigate()
  const vendorCtx = useVendorFilter?.() || {}
  const vendorParam = vendorCtx?.selectedVendor ? `?vendor_id=${vendorCtx.selectedVendor}` : ''
  const deps = [refreshKey, vendorCtx?.selectedVendor]

  const { data: resumen, loading: lRes } = useFetch(`/ventas/resumen${vendorParam}`, deps)
  const { data: ventasHoy }              = useFetch(`/ventas/hoy${vendorParam}`,     deps)
  const { data: caja }                   = useFetch(`/caja`,                          deps)
  const { data: alertas }                = useFetch(`/inventario/bajo`,               deps)

  const ventasHoyArr = Array.isArray(ventasHoy) ? ventasHoy : []

  // ── Derivados en cliente ────────────────────────────────────────────────────
  const totalGastos = useMemo(() => {
    const gastos = caja?.gastos || []
    return gastos.reduce((acc, g) => acc + (g.monto || 0), 0)
  }, [caja])

  const numGastos = caja?.gastos?.length || 0

  const metodosPago = useMemo(() => {
    const tot = { efectivo: 0, transferencia: 0, fiado: 0, datafono: 0, otro: 0 }
    let suma = 0
    for (const v of ventasHoyArr) {
      const m = (v.metodo_pago || '').toLowerCase()
      const monto = Number(v.total) || 0
      suma += monto
      if (m.includes('efectivo')) tot.efectivo += monto
      else if (m.includes('transf')) tot.transferencia += monto
      else if (m.includes('fiado') || m.includes('credito')) tot.fiado += monto
      else if (m.includes('datafono') || m.includes('tarjeta')) tot.datafono += monto
      else tot.otro += monto
    }
    return { tot, suma }
  }, [ventasHoyArr])

  const ultimas = useMemo(() => {
    return [...ventasHoyArr]
      .sort((a, b) => String(b.hora || '').localeCompare(String(a.hora || '')))
      .slice(0, 8)
  }, [ventasHoyArr])

  const totalHoy   = resumen?.total_hoy   ?? 0
  const ticketProm = resumen?.ticket_prom ?? 0
  const totalSem   = resumen?.total_semana ?? 0
  const totalMes   = resumen?.total_mes ?? 0
  const pedidosHoy = resumen?.pedidos_hoy ?? ventasHoyArr.length

  const alertasArr = Array.isArray(alertas) ? alertas : (alertas?.productos || [])
  const stockBajo  = alertasArr.slice(0, 4)

  const cajaAbierta = !!caja?.abierta
  const aperturaCaja = caja?.monto_apertura || 0
  const efectivoEsperado = caja?.efectivo_esperado || 0
  const delta = efectivoEsperado - aperturaCaja

  return (
    <div className="space-y-5">
      {/* Header de bienvenida */}
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Hoy</h1>
          <p className="text-sm text-muted-foreground capitalize">
            {new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'America/Bogota' })}
          </p>
        </div>
        <div className="hidden md:flex gap-2">
          <Button size="sm" onClick={() => navigate('/ventas')}>
            <Plus className="size-4" /> Nueva venta
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/gastos')}>
            <Plus className="size-4" /> Gasto
          </Button>
        </div>
      </header>

      {/* Fila 1 — Cifras del día */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <BentoCard
          label="Ventas hoy"
          value={cop(totalHoy)}
          icon={ShoppingCart}
          sub={`${pedidosHoy} ventas · ticket prom. ${cop(ticketProm)}`}
          loading={lRes}
          accent
        />
        <BentoCard
          label="Caja"
          value={cajaAbierta ? 'Abierta' : 'Cerrada'}
          icon={Wallet}
          sub={cajaAbierta
            ? `Apertura ${cop(aperturaCaja)} · esperado ${cop(efectivoEsperado)}`
            : 'Pendiente de apertura'}
          delta={cajaAbierta ? delta : null}
          actionLabel={cajaAbierta ? 'Cerrar caja' : 'Abrir caja'}
          onAction={() => navigate('/caja')}
        />
        <BentoCard
          label="Gastos hoy"
          value={cop(totalGastos)}
          icon={Receipt}
          sub={`${numGastos} ${numGastos === 1 ? 'gasto' : 'gastos'}`}
          actionLabel="+ Gasto"
          onAction={() => navigate('/gastos')}
        />
      </div>

      {/* Fila 2 — Acumulados + métodos de pago */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Acumulados</h2>
            <button onClick={() => navigate('/resultados')} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
              Ver resultados <ArrowRight className="size-3" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-6">
            <Acumulado label="Semana" value={totalSem} hist={resumen?.historico_7d} />
            <Acumulado label="Mes"    value={totalMes} hist={resumen?.historico_mes} />
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Métodos de pago (hoy)</h2>
            <span className="text-xs text-muted-foreground tabular">{cop(metodosPago.suma)}</span>
          </div>
          <div className="space-y-2.5">
            <MetodoBar label="Efectivo"      monto={metodosPago.tot.efectivo}      total={metodosPago.suma} />
            <MetodoBar label="Transferencia" monto={metodosPago.tot.transferencia} total={metodosPago.suma} />
            <MetodoBar label="Datáfono"      monto={metodosPago.tot.datafono}      total={metodosPago.suma} />
            <MetodoBar label="Fiado"         monto={metodosPago.tot.fiado}         total={metodosPago.suma} />
          </div>
        </Card>
      </div>

      {/* Fila 3 — Últimas ventas */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Últimas ventas</h2>
          <button onClick={() => navigate('/historial')} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
            Ver historial <ArrowRight className="size-3" />
          </button>
        </div>
        {ultimas.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Sin ventas registradas hoy.</p>
        ) : (
          <ul className="divide-y divide-border-subtle">
            {ultimas.map((v, i) => (
              <li key={`${v.consecutivo}-${i}`} className="py-2 flex items-center gap-3 text-sm">
                <span className="text-xs text-muted-foreground tabular w-14">#{v.consecutivo ?? '—'}</span>
                <span className="text-xs text-muted-foreground tabular w-12">{(v.hora || '').slice(0, 5)}</span>
                <span className="flex-1 truncate">{v.producto || v.cliente || '—'}</span>
                <span className="text-xs text-muted-foreground hidden sm:inline">{v.metodo_pago || '—'}</span>
                <span className="tabular font-medium">{cop(v.total)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Fila 4 — Stock + (futuro) fiados */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-2">
              <AlertTriangle className="size-3.5 text-warning" />
              Alertas de stock
              {stockBajo.length > 0 && (
                <Badge variant="secondary" className="ml-1">{alertasArr.length}</Badge>
              )}
            </h2>
            <button onClick={() => navigate('/inventario')} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
              Ver inventario <ArrowRight className="size-3" />
            </button>
          </div>
          {stockBajo.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Stock sin alertas.</p>
          ) : (
            <ul className="space-y-2">
              {stockBajo.map((p, i) => (
                <li key={i} className="flex items-center gap-3 text-sm">
                  <Package className="size-4 text-muted-foreground shrink-0" />
                  <span className="flex-1 truncate">{p.nombre || p.producto || '—'}</span>
                  <span className="tabular text-warning font-medium">
                    {num(p.stock ?? p.cantidad ?? 0)} {p.unidad || ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-2">
              <Users className="size-3.5" />
              Quick actions
            </h2>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <QuickAction label="Nueva venta"  onClick={() => navigate('/ventas')} />
            <QuickAction label="Gasto"        onClick={() => navigate('/gastos')} />
            <QuickAction label="Compra"       onClick={() => navigate('/compras')} />
            <QuickAction label="Cliente"      onClick={() => navigate('/clientes')} />
            <QuickAction label="Cerrar caja"  onClick={() => navigate('/caja')} variant="outline" />
            <QuickAction label="Inventario"   onClick={() => navigate('/inventario')} variant="outline" />
          </div>
        </Card>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

function BentoCard({ label, value, icon: Icon, sub, delta, accent, loading, actionLabel, onAction }) {
  return (
    <Card className={cn('p-5 relative overflow-hidden', accent && 'border-primary/30')}>
      {accent && <div className="absolute inset-x-0 top-0 h-[2px] bg-primary/60" />}
      <div className="flex items-start justify-between mb-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        <Icon className={cn('size-4', accent ? 'text-primary' : 'text-muted-foreground')} />
      </div>
      <div className={cn('text-3xl font-semibold tracking-tight tabular leading-none', loading && 'opacity-50')}>
        {value}
      </div>
      {sub && <p className="mt-2 text-xs text-muted-foreground">{sub}</p>}
      {delta !== null && delta !== undefined && (
        <div className={cn('mt-2 inline-flex items-center gap-1 text-xs tabular',
          delta >= 0 ? 'text-success' : 'text-danger')}>
          {delta >= 0 ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
          <span>{delta >= 0 ? '+' : ''}{cop(delta)}</span>
        </div>
      )}
      {actionLabel && (
        <button onClick={onAction} className="mt-3 text-xs text-primary hover:underline inline-flex items-center gap-1">
          {actionLabel} <ArrowRight className="size-3" />
        </button>
      )}
    </Card>
  )
}

function Acumulado({ label, value, hist }) {
  const series = Array.isArray(hist) ? hist : []
  const last = series.length > 0 ? Number(series[series.length - 1]?.total ?? series[series.length - 1]) : 0
  const prev = series.length > 1 ? Number(series[series.length - 2]?.total ?? series[series.length - 2]) : 0
  const pct  = prev > 0 ? ((last - prev) / prev) * 100 : 0
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">{label}</div>
      <div className="text-2xl font-semibold tracking-tight tabular">{cop(value)}</div>
      {Math.abs(pct) > 0.5 && (
        <div className={cn('mt-1 inline-flex items-center gap-1 text-xs tabular',
          pct >= 0 ? 'text-success' : 'text-danger')}>
          {pct >= 0 ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
          <span>{pct >= 0 ? '+' : ''}{pct.toFixed(1)}%</span>
        </div>
      )}
    </div>
  )
}

function MetodoBar({ label, monto, total }) {
  const pct = total > 0 ? Math.round((monto / total) * 100) : 0
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-24 text-muted-foreground">{label}</span>
      <div className="flex-1 h-1.5 bg-surface-2 rounded-full overflow-hidden">
        <div
          className="h-full bg-primary/70 rounded-full transition-all duration-base"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 text-right tabular text-muted-foreground">{pct}%</span>
      <span className="w-24 text-right tabular font-medium">{cop(monto)}</span>
    </div>
  )
}

function QuickAction({ label, onClick, variant = 'secondary' }) {
  return (
    <Button variant={variant} size="sm" onClick={onClick} className="justify-start">
      <Plus className="size-3.5" />
      <span>{label}</span>
    </Button>
  )
}
