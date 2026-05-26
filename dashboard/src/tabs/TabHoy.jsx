/*
 * TabHoy — cockpit operativo, landing del dashboard.
 * Wave 1 Fase B "Aurora Ferretera" + iteración post-feedback:
 *   - KPIs principales compactos (3 cards: Ventas / Caja / Gastos)
 *   - Strip de métricas secundarias (Pedidos / Ticket prom / Semana / Mes)
 *   - Hero: AreaChart de evolución + feed live (últimas ventas)
 *   - Operativa: Métodos de pago + Top productos + Stock bajo
 *   - Quick actions
 * Datos derivados en cliente desde endpoints existentes — no toca backend.
 *
 * NOTA shape /ventas/hoy: el endpoint retorna { fecha, ventas, total, fuente }.
 * Cada venta usa `metodo` (no `metodo_pago`) y `vendedor`.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AreaChart, Area, ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip,
} from 'recharts'
import {
  ArrowRight, Plus, AlertTriangle,
  ShoppingCart, Wallet, Receipt, Package, Search, Activity,
  CreditCard, Calculator, CalendarRange, CalendarDays, ListOrdered,
} from 'lucide-react'
import { useFetch, cop, num } from '@/components/shared.jsx'
import { useVendorFilter } from '@/hooks/useVendorFilter.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import KpiCard from '@/components/KpiCard.jsx'
import { cn } from '@/lib/utils'

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE PRINCIPAL
// ─────────────────────────────────────────────────────────────────────────────

export default function TabHoy({ refreshKey }) {
  const navigate    = useNavigate()
  const vendorCtx   = useVendorFilter?.() || {}
  const vendorParam = vendorCtx?.selectedVendor ? `?vendor_id=${vendorCtx.selectedVendor}` : ''
  const deps        = [refreshKey, vendorCtx?.selectedVendor]

  const { data: resumen, loading: lRes } = useFetch(`/ventas/resumen${vendorParam}`, deps)
  const { data: ventasHoyRaw }           = useFetch(`/ventas/hoy${vendorParam}`,     deps)
  const { data: caja }                   = useFetch(`/caja`,                          deps)
  const { data: alertas }                = useFetch(`/inventario/bajo`,               deps)

  // /ventas/hoy → { fecha, ventas: [...], total, fuente }. Defensivo por si cambia.
  const ventasHoyArr = useMemo(() => {
    if (Array.isArray(ventasHoyRaw?.ventas)) return ventasHoyRaw.ventas
    if (Array.isArray(ventasHoyRaw))         return ventasHoyRaw
    return []
  }, [ventasHoyRaw])

  // ── Derivados en cliente ───────────────────────────────────────────────────
  const totalGastos = useMemo(() => {
    const gastos = caja?.gastos || []
    return gastos.reduce((acc, g) => acc + (g.monto || 0), 0)
  }, [caja])
  const numGastos = caja?.gastos?.length || 0

  const ultimas = useMemo(() => {
    return [...ventasHoyArr]
      .sort((a, b) => String(b.hora || '').localeCompare(String(a.hora || '')))
      .slice(0, 6)
  }, [ventasHoyArr])

  // Top productos del día (agregado en cliente)
  const topProductos = useMemo(() => {
    const acc = {}
    for (const v of ventasHoyArr) {
      const nombre = String(v.producto || '').trim()
      if (!nombre || nombre.length < 2) continue
      const monto = Number(v.total) || 0
      const cant  = Number(v.cantidad) || 1
      if (!acc[nombre]) acc[nombre] = { nombre, monto: 0, cant: 0 }
      acc[nombre].monto += monto
      acc[nombre].cant  += cant
    }
    const arr  = Object.values(acc).sort((a, b) => b.monto - a.monto).slice(0, 5)
    const max  = arr[0]?.monto || 1
    return arr.map(p => ({ ...p, pct: Math.max(8, Math.round((p.monto / max) * 100)) }))
  }, [ventasHoyArr])

  // Métodos de pago (agregado en cliente desde /ventas/hoy)
  const metodosPago = useMemo(() => {
    const acc = {}
    for (const v of ventasHoyArr) {
      const raw = String(v.metodo || '').trim().toLowerCase()
      const key =
        raw.includes('efect')   ? 'Efectivo' :
        raw.includes('nequi')   ? 'Nequi' :
        raw.includes('transf')  ? 'Transferencia' :
        raw.includes('datafono') || raw.includes('tarj') ? 'Tarjeta' :
        raw.includes('fiado') || raw.includes('credit')  ? 'Fiado' :
        raw === '' || raw === '—' ? 'Sin registrar' : 'Otro'
      acc[key] = (acc[key] || 0) + (Number(v.total) || 0)
    }
    const arr = Object.entries(acc).map(([nombre, monto]) => ({ nombre, monto }))
      .sort((a, b) => b.monto - a.monto)
    const total = arr.reduce((a, m) => a + m.monto, 0)
    return arr.map(m => ({ ...m, pct: total > 0 ? Math.round((m.monto / total) * 100) : 0 }))
  }, [ventasHoyArr])
  const totalMetodos = metodosPago.reduce((a, m) => a + m.monto, 0)

  const totalHoy     = resumen?.total_hoy     ?? 0
  const ticketProm   = resumen?.ticket_prom   ?? 0
  const pedidosHoy   = resumen?.pedidos_hoy   ?? ventasHoyArr.length
  const totalSemana  = resumen?.total_semana  ?? 0
  const totalMes     = resumen?.total_mes     ?? 0

  const alertasArr = Array.isArray(alertas) ? alertas : (alertas?.productos || [])
  const stockBajo  = alertasArr.slice(0, 5)

  const cajaAbierta      = !!caja?.abierta
  const aperturaCaja     = caja?.monto_apertura || 0
  const horaApertura     = caja?.hora_apertura || caja?.fecha_apertura || ''
  const numMovs          = (ventasHoyArr.length + numGastos) || 0

  // Serie historico_7d para chart hero y sparkline de ventas
  const historico7d  = Array.isArray(resumen?.historico_7d)  ? resumen.historico_7d  : []
  const historicoMes = Array.isArray(resumen?.historico_mes) ? resumen.historico_mes : []

  // Delta vs ayer (último vs penúltimo del histórico 7d)
  const deltaAyer = useMemo(() => {
    if (historico7d.length < 2) return null
    const last = Number(historico7d[historico7d.length - 1]?.total ?? 0)
    const prev = Number(historico7d[historico7d.length - 2]?.total ?? 0)
    if (prev <= 0) return null
    return ((last - prev) / prev) * 100
  }, [historico7d])

  return (
    <div className="space-y-4">
      {/* KPI STRIP — 3 cards principales con topAccent + iconStyle filled */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <KpiCard
          tone="primary"
          label="Ventas hoy"
          value={cop(totalHoy)}
          icon={ShoppingCart}
          loading={lRes}
          sub={`${pedidosHoy} ${pedidosHoy === 1 ? 'venta' : 'ventas'}`}
          deltaPct={deltaAyer}
          spark={historico7d}
          topAccent
          iconStyle="filled"
          heroValue
        />
        <KpiCard
          tone={cajaAbierta ? 'success' : 'warning'}
          label="Caja"
          icon={Wallet}
          onClick={() => navigate('/caja')}
          actionLabel={cajaAbierta ? 'Cerrar caja' : 'Abrir caja'}
          value={
            <span className="inline-flex items-baseline gap-2">
              <Badge variant="secondary" className={cn(
                'h-5 text-[10px] font-semibold uppercase tracking-wide',
                cajaAbierta ? 'bg-success/10 text-success border-success/20' : 'bg-warning/10 text-warning border-warning/20'
              )}>
                {cajaAbierta ? '● Abierta' : 'Cerrada'}
              </Badge>
              {cajaAbierta && horaApertura && (
                <span className="text-sm tabular text-muted-foreground font-medium">
                  {String(horaApertura).slice(0, 5)}
                </span>
              )}
            </span>
          }
          sub={cajaAbierta
            ? `Base ${cop(aperturaCaja)} · ${numMovs} movs`
            : 'Pendiente de apertura'}
          topAccent
          iconStyle="filled"
        />
        <KpiCard
          tone="danger"
          label="Gastos hoy"
          value={cop(totalGastos)}
          icon={Receipt}
          onClick={() => navigate('/gastos')}
          actionLabel="Registrar gasto"
          sub={`${numGastos} ${numGastos === 1 ? 'registro' : 'registros'}`}
          topAccent
          iconStyle="filled"
        />
      </div>

      {/* MINI METRIC STRIP — 4 KpiCards con topAccent, tones contrastantes */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          tone="primary"
          icon={ListOrdered}
          label="Pedidos hoy"
          value={num(pedidosHoy)}
          sub={pedidosHoy > 0 ? `de ${cop(totalHoy)}` : 'sin ventas'}
          compact
          topAccent
          iconStyle="filled"
        />
        <KpiCard
          tone="info"
          icon={Calculator}
          label="Ticket prom."
          value={cop(ticketProm)}
          sub="últimos 7 días"
          compact
          topAccent
          iconStyle="filled"
        />
        <KpiCard
          tone="success"
          icon={CalendarRange}
          label="Total semana"
          value={cop(totalSemana)}
          sub="últimos 7 días"
          compact
          topAccent
          iconStyle="filled"
        />
        <KpiCard
          tone="warning"
          icon={CalendarDays}
          label="Total mes"
          value={cop(totalMes)}
          sub="mes en curso"
          compact
          topAccent
          iconStyle="filled"
        />
      </div>

      {/* HERO ZONE — Chart (2/3) + Feed live (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <EvolucionChart
          historico7d={historico7d}
          historicoMes={historicoMes}
          loading={lRes}
        />
        <FeedLive
          ventas={ultimas}
          onMore={() => navigate('/historial')}
        />
      </div>

      {/* OPERATIVA — Métodos pago + Top productos + Stock bajo */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <MetodosPago items={metodosPago} total={totalMetodos} />
        <TopProductos
          items={topProductos}
          onMore={() => navigate('/top-productos')}
        />
        <StockBajo
          items={stockBajo}
          total={alertasArr.length}
          onMore={() => navigate('/inventario')}
        />
      </div>

      {/* QUICK ACTIONS — full-width strip */}
      <QuickActions navigate={navigate} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EVOLUCIÓN — chart hero con toggle 7d / 30d
// ─────────────────────────────────────────────────────────────────────────────

function EvolucionChart({ historico7d, historicoMes, loading }) {
  const [periodo, setPeriodo] = useState('7d')

  const data = useMemo(() => {
    const src = periodo === '7d' ? historico7d : historicoMes
    return (src || []).map(d => {
      const fecha = String(d.fecha || '').slice(0, 10)
      const dia   = fecha ? new Date(fecha + 'T12:00:00').toLocaleDateString('es-CO', { weekday: 'short', day: 'numeric' }) : ''
      return { fecha, dia, total: Number(d.total) || 0 }
    })
  }, [historico7d, historicoMes, periodo])

  const totalPeriodo = data.reduce((acc, d) => acc + d.total, 0)
  const promDia      = data.length > 0 ? totalPeriodo / data.length : 0

  return (
    <Card className="lg:col-span-2 p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Evolución de ventas</h2>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-xl font-semibold tracking-tight tabular">{cop(totalPeriodo)}</span>
            <span className="text-[11px] text-muted-foreground">
              acumulado · prom. {cop(promDia)}/día
            </span>
          </div>
        </div>
        <div className="flex gap-1 bg-surface-2 p-1 rounded-md">
          <PeriodPill active={periodo === '7d'}  onClick={() => setPeriodo('7d')}>7d</PeriodPill>
          <PeriodPill active={periodo === '30d'} onClick={() => setPeriodo('30d')}>30d</PeriodPill>
        </div>
      </div>

      {loading ? (
        <div className="h-[200px] grid place-items-center text-sm text-muted-foreground">Cargando…</div>
      ) : data.length === 0 ? (
        <div className="h-[200px] grid place-items-center text-sm text-muted-foreground">Sin datos para este período.</div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="hoyEvolGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor="hsl(var(--accent))" stopOpacity={0.15} />
                <stop offset="95%" stopColor="hsl(var(--accent))" stopOpacity={0}    />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="hsl(var(--border-subtle))" vertical={false} strokeDasharray="3 3" />
            <XAxis
              dataKey="dia"
              tick={{ fill: 'hsl(var(--text-muted))', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickMargin={8}
              interval={periodo === '30d' ? 'preserveStartEnd' : 0}
              minTickGap={20}
            />
            <YAxis
              tick={{ fill: 'hsl(var(--text-muted))', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
              width={42}
            />
            <Tooltip
              contentStyle={{
                background:    'hsl(var(--bg-surface))',
                border:        '1px solid hsl(var(--border))',
                borderRadius:  8,
                color:         'hsl(var(--text-primary))',
                fontSize:      11,
                boxShadow:     '0 4px 12px rgba(0,0,0,0.08)',
              }}
              labelStyle={{ color: 'hsl(var(--text-muted))', marginBottom: 4 }}
              formatter={v => [cop(v), 'Ventas']}
              cursor={{ stroke: 'hsl(var(--accent))', strokeWidth: 1, strokeDasharray: '4 4' }}
            />
            <Area
              type="monotone"
              dataKey="total"
              stroke="hsl(var(--accent))"
              strokeWidth={2}
              fill="url(#hoyEvolGrad)"
              activeDot={{ r: 4, fill: 'hsl(var(--accent))', stroke: 'hsl(var(--bg-surface))', strokeWidth: 2 }}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}

function PeriodPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 text-[11px] font-medium rounded transition-colors',
        active
          ? 'bg-surface text-foreground shadow-xs'
          : 'text-muted-foreground hover:text-foreground'
      )}
    >
      {children}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FEED LIVE — últimas ventas con pulse-dot y badge por método de pago
// ─────────────────────────────────────────────────────────────────────────────

function metodoTone(metodo) {
  const m = String(metodo || '').toLowerCase()
  if (m.includes('efectivo'))                       return 'bg-success/10 text-success border-success/20'
  if (m.includes('transf'))                         return 'bg-warning/10 text-warning border-warning/20'
  if (m.includes('nequi'))                          return 'bg-info/10 text-info border-info/20'
  if (m.includes('datafono') || m.includes('tarj')) return 'bg-info/10 text-info border-info/20'
  if (m.includes('fiado') || m.includes('credito')) return 'bg-danger/10 text-danger border-danger/20'
  return 'bg-surface-2 text-muted-foreground border-border'
}

function FeedLive({ ventas, onMore }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-2">
          Últimas ventas
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full rounded-full bg-success/60 animate-ping opacity-75"/>
            <span className="relative inline-flex size-2 rounded-full bg-success"/>
          </span>
        </h2>
        <button onClick={onMore} className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          ver todas <ArrowRight className="size-3"/>
        </button>
      </div>
      {ventas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">Sin ventas registradas hoy.</p>
      ) : (
        <ul className="divide-y divide-border-subtle">
          {ventas.map((v, i) => (
            <li key={`${v.num || v.consecutivo}-${i}`} className="py-2 flex items-center gap-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-[11px] text-muted-foreground tabular">{(v.hora || '').slice(0, 5)}</span>
                  <span className="text-[13px] font-semibold tabular">{cop(v.total)}</span>
                </div>
                <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                  {v.producto || v.cliente || '—'}
                </div>
              </div>
              <Badge variant="outline" className={cn('text-[10px] h-5 px-1.5 shrink-0 capitalize', metodoTone(v.metodo))}>
                {v.metodo || '—'}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MÉTODOS DE PAGO — agregado del día con barras de %
// ─────────────────────────────────────────────────────────────────────────────

const METODO_BAR_COLORS = {
  'Efectivo':       'hsl(var(--success))',
  'Nequi':          'hsl(var(--accent))',
  'Transferencia':  'hsl(var(--accent))',
  'Tarjeta':        'hsl(var(--info))',
  'Fiado':          'hsl(var(--warning))',
  'Sin registrar':  'hsl(var(--text-muted))',
  'Otro':           'hsl(var(--text-muted))',
}

function MetodosPago({ items, total }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1.5">
          <CreditCard className="size-3.5"/>
          Métodos de pago · Hoy
        </h2>
        {total > 0 && (
          <span className="text-[11px] text-muted-foreground tabular">{cop(total)}</span>
        )}
      </div>
      {items.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Sin ventas hoy.</p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((m, i) => {
            const color = METODO_BAR_COLORS[m.nombre] || 'hsl(var(--text-muted))'
            return (
              <li key={i}>
                <div className="flex items-baseline justify-between mb-1 text-[12px]">
                  <span className="font-medium truncate">{m.nombre}</span>
                  <span className="tabular font-semibold shrink-0">{cop(m.monto)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1 rounded-full bg-surface-2 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-base"
                      style={{ width: `${Math.max(4, m.pct)}%`, background: color }}
                    />
                  </div>
                  <span className="text-[10px] text-muted-foreground tabular w-9 text-right shrink-0">{m.pct}%</span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TOP PRODUCTOS, STOCK BAJO, QUICK ACTIONS
// ─────────────────────────────────────────────────────────────────────────────

function TopProductos({ items, onMore }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Top productos hoy</h2>
        <button onClick={onMore} className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          ver todos <ArrowRight className="size-3"/>
        </button>
      </div>
      {items.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Sin ventas hoy.</p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((p, i) => (
            <li key={i}>
              <div className="flex items-baseline justify-between mb-1 text-[12px]">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-muted-foreground tabular w-4 shrink-0">{i + 1}</span>
                  <span className="font-medium truncate">{p.nombre}</span>
                </div>
                <span className="tabular font-semibold shrink-0">{cop(p.monto)}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1 rounded-full bg-surface-2 overflow-hidden">
                  <div className="h-full rounded-full bg-primary/80 transition-all duration-base" style={{ width: `${p.pct}%` }}/>
                </div>
                <span className="text-[10px] text-muted-foreground tabular w-12 text-right shrink-0">{num(p.cant)} ud</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function StockBajo({ items, total, onMore }) {
  const critico = items.filter(p => Number(p.stock ?? p.cantidad ?? 0) <= 5).length
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1.5">
          <AlertTriangle className="size-3.5 text-warning"/>
          Stock bajo
        </h2>
        {total > 0 && (
          <Badge variant="outline" className={cn('h-5 text-[10px]',
            critico > 0 ? 'bg-primary/10 text-primary border-primary/20' : 'bg-warning/10 text-warning border-warning/20'
          )}>
            {total} {total === 1 ? 'alerta' : 'alertas'}
          </Badge>
        )}
      </div>
      {items.length === 0 ? (
        <div className="py-8 flex flex-col items-center gap-2 text-muted-foreground">
          <AlertTriangle className="size-6 text-warning opacity-60" />
          <p className="text-sm">Stock sin alertas.</p>
        </div>
      ) : (
        <>
          <ul className="divide-y divide-border-subtle">
            {items.map((p, i) => {
              const stock = Number(p.stock ?? p.cantidad ?? 0)
              const isCrit = stock <= 5
              return (
                <li key={i} className="py-1.5 flex items-center gap-2 text-[12px]">
                  <Package className="size-3.5 text-muted-foreground shrink-0"/>
                  <span className="flex-1 truncate">{p.nombre || p.producto || '—'}</span>
                  <span className={cn('tabular font-semibold shrink-0', isCrit ? 'text-primary' : 'text-warning')}>
                    {num(stock)} {p.unidad || 'ud'}
                  </span>
                </li>
              )
            })}
          </ul>
          <button onClick={onMore} className="w-full mt-3 text-[11px] text-primary hover:underline font-medium inline-flex items-center justify-center gap-1">
            ver todos en inventario <ArrowRight className="size-3"/>
          </button>
        </>
      )}
    </Card>
  )
}

function QuickActions({ navigate }) {
  const actions = [
    { label: 'Nueva venta', icon: Plus,         tone: 'primary',  to: '/ventas' },
    { label: 'Gasto',       icon: Receipt,      tone: 'warning',  to: '/gastos' },
    { label: 'Cliente',     icon: Search,       tone: 'info',     to: '/clientes' },
    { label: 'Inventario',  icon: Package,      tone: 'success',  to: '/inventario' },
  ]
  const toneStyles = {
    primary: { color: 'hsl(var(--accent))',  bg: 'bg-primary/10'  },
    warning: { color: 'hsl(var(--warning))', bg: 'bg-warning/10'  },
    info:    { color: 'hsl(var(--info))',    bg: 'bg-info/10'     },
    success: { color: 'hsl(var(--success))', bg: 'bg-success/10'  },
  }
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1.5">
          <Activity className="size-3.5"/>
          Acciones rápidas
        </h2>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {actions.map(a => {
          const t = toneStyles[a.tone]
          const Icon = a.icon
          return (
            <button
              key={a.label}
              onClick={() => navigate(a.to)}
              className={cn(
                'group flex items-center gap-2.5 p-3 rounded-md border border-border bg-surface',
                'hover:border-primary/40 hover:bg-primary/[0.03] transition-colors text-left'
              )}
            >
              <span className={cn('grid place-items-center rounded-md size-8 shrink-0', t.bg)} style={{ color: t.color }}>
                <Icon className="size-4"/>
              </span>
              <span className="text-[12px] font-medium truncate">{a.label}</span>
            </button>
          )
        })}
      </div>
    </Card>
  )
}
