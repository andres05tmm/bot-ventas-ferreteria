/*
 * TabResumen — KPIs históricos (degradado de landing a sub-tab en Fase 4).
 * Wave 1.b: migrado a primitives shadcn + tokens semantic.
 * Lógica de datos sin cambios (endpoints /ventas/resumen /ventas/hoy /ventas/top /inventario/bajo).
 */
import { useState, useEffect } from 'react'
import {
  AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  useFetch, cop, num, API_BASE, useIsMobile,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import {
  Wallet, Receipt, AlertTriangle, Calculator, CalendarRange, CalendarDays,
  TrendingUp, TrendingDown, Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const KPI_ICONS = { Wallet, Receipt, AlertTriangle, Calculator, CalendarRange, CalendarDays }

const METODO_COLORS = ['hsl(var(--accent))','hsl(var(--success))','#0284C7','#EA580C','#7c3aed','#71717A']
const MEDALLAS      = ['🥇','🥈','🥉']

function fmtFecha(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

function agruparMetodos(ventas) {
  const acc = {}
  ;(ventas || []).forEach(v => {
    const raw = String(v.metodo || '').trim().toLowerCase()
    const key =
      raw.includes('efect')  ? 'Efectivo' :
      raw.includes('nequi')  ? 'Nequi' :
      raw.includes('billet') ? 'Billetera' :
      raw.includes('transf') ? 'Transferencia' :
      raw.includes('tarjet') ? 'Tarjeta' :
      raw === '' || raw === '—' ? 'Sin registrar' : 'Otro'
    acc[key] = (acc[key] || 0) + (parseFloat(v.total) || 0)
  })
  return Object.entries(acc).map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
}

function agruparVendedores(ventas) {
  const acc = {}
  ;(ventas || []).forEach(v => {
    const key = String(v.vendedor || '').trim() || 'Sin asignar'
    acc[key] = (acc[key] || 0) + (parseFloat(v.total) || 0)
  })
  return Object.entries(acc)
    .map(([nombre, total]) => ({ nombre, total }))
    .sort((a, b) => b.total - a.total)
}

function formatCantidadTop(unidades, unidad_medida) {
  const u = (unidad_medida || 'Unidad').toLowerCase().replace('ó', 'o')
  if (u === 'gramos' || u === 'grm' || u === 'g') {
    if (unidades >= 1000) return `${(unidades / 1000).toFixed(1).replace(/\.0$/, '')} kg`
    return `${num(unidades)} g`
  }
  if (u === 'kg')                                return `${num(unidades)} kg`
  if (u === 'mts' || u === 'cms')                return `${num(unidades)} ${u}`
  if (u === 'galon' || u === 'lt' || u === 'lts') return `${num(unidades)} gal`
  return `${num(unidades)} uds`
}

// ────────────────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, pill, pillTone = 'neutral', icon }) {
  const Icon = KPI_ICONS[icon]
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        {Icon && <Icon className="size-4 text-muted-foreground" />}
      </div>
      <div className="text-xl font-semibold tracking-tight tabular leading-none">{value}</div>
      {sub && <p className="mt-2 text-xs text-muted-foreground">{sub}</p>}
      {pill && (
        <span className={cn(
          'inline-block mt-2 text-[10px] px-2 py-0.5 rounded-full font-medium',
          pillTone === 'success' && 'bg-success/10 text-success border border-success/30',
          pillTone === 'warning' && 'bg-warning/10 text-warning border border-warning/30',
          pillTone === 'accent'  && 'bg-primary-soft text-primary border border-primary/30',
          pillTone === 'neutral' && 'bg-surface-2 text-muted-foreground border border-border',
        )}>
          {pill}
        </span>
      )}
    </Card>
  )
}

function MetodoRow({ m, total, color }) {
  const pct = total > 0 ? Math.round((m.value / total) * 100) : 0
  return (
    <div className="flex items-center gap-3 py-2 text-sm border-b border-border-subtle last:border-0">
      <span className="flex-1 truncate text-foreground">{m.name}</span>
      <div className="w-24 h-1.5 bg-surface-2 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-base" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-10 text-right text-xs text-muted-foreground tabular">{pct}%</span>
      <span className="w-24 text-right tabular font-medium">{cop(m.value)}</span>
    </div>
  )
}

function VendedorRow({ v, i, maxTotal }) {
  const pct = maxTotal > 0 ? Math.round((v.total / maxTotal) * 100) : 0
  return (
    <div className="flex items-center gap-3 py-2 text-sm border-b border-border-subtle last:border-0">
      <span className="w-7 text-center">
        {i < 3 ? <span className="text-base">{MEDALLAS[i]}</span> : <span className="text-xs text-muted-foreground">#{i+1}</span>}
      </span>
      <span className="flex-1 truncate">{v.nombre}</span>
      <div className="w-24 h-1.5 bg-surface-2 rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-base', i === 0 ? 'bg-primary' : 'bg-muted-foreground/60')} style={{ width: `${pct}%` }} />
      </div>
      <span className={cn('w-24 text-right tabular font-medium', i === 0 && 'text-primary')}>{cop(v.total)}</span>
    </div>
  )
}

function TopProductoRow({ p, i, max }) {
  const pct = max > 0 ? Math.round((p.ingresos / max) * 100) : 0
  return (
    <div className="flex items-center gap-3 py-2 text-sm border-b border-border-subtle last:border-0">
      <span className="size-6 rounded-md bg-primary-soft text-primary text-xs font-bold grid place-items-center shrink-0">
        {i + 1}
      </span>
      <span className="flex-1 truncate">{p.producto}</span>
      <span className="w-24 text-right text-xs text-muted-foreground tabular">{formatCantidadTop(p.unidades, p.unidad_medida)}</span>
      <div className="w-20 h-1.5 bg-surface-2 rounded-full overflow-hidden hidden md:block">
        <div className="h-full bg-primary/70 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-24 text-right tabular font-medium">{cop(p.ingresos)}</span>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────

export default function TabResumen({ refreshKey }) {
  const isMobile = useIsMobile()
  const [periodo, setPeriodo] = useState('semana')
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()
  const vendorParam = selectedVendor ? `?vendor_id=${selectedVendor}` : ''

  const { data: resumen, loading: lRes, error: eRes } = useFetch(`/ventas/resumen${vendorParam}`, [refreshKey, selectedVendor])
  const { data: alertasData } = useFetch('/inventario/bajo', [refreshKey])
  const { data: ventasHoy }   = useFetch(`/ventas/hoy${vendorParam}`, [refreshKey, selectedVendor])

  const [top5, setTop5] = useState(null)
  useEffect(() => {
    let cancelled = false
    const url = `${API_BASE}/ventas/top?periodo=semana${selectedVendor ? `&vendor_id=${selectedVendor}` : ''}`
    authFetch(url)
      .then(r => r.json())
      .then(d => { if (!cancelled) setTop5(d.top?.slice(0, 5) || []) })
      .catch(() => { if (!cancelled) setTop5([]) })
    return () => { cancelled = true }
  }, [refreshKey, selectedVendor]) // eslint-disable-line react-hooks/exhaustive-deps

  if (lRes) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="size-5 animate-spin mr-2" /> Cargando resumen…
      </div>
    )
  }
  if (eRes) {
    return (
      <Card className="p-4 border-destructive/40 bg-destructive/5 text-destructive text-sm">
        Error cargando resumen: {eRes}
      </Card>
    )
  }

  const r          = resumen || {}
  const rawHist    = periodo === 'semana' ? (r.historico_7d || []) : (r.historico_mes || [])
  const chartData  = rawHist.map(d => ({ dia: fmtFecha(d.fecha), ventas: d.total || 0 }))
  const totalChart = chartData.reduce((a, d) => a + d.ventas, 0)
  const maxTop5Ing = top5?.[0]?.ingresos || 1

  const ventasHoyArr   = Array.isArray(ventasHoy?.ventas) ? ventasHoy.ventas : []
  const metodosData    = agruparMetodos(ventasHoyArr)
  const vendedoresData = agruparVendedores(ventasHoyArr)
  const totalMetodos   = metodosData.reduce((a, m) => a + m.value, 0)
  const maxVendedor    = vendedoresData[0]?.total || 1

  const promAntes = chartData.length > 1
    ? chartData.slice(0, -1).reduce((a, d) => a + d.ventas, 0) / (chartData.length - 1)
    : 0
  const tendencia = promAntes > 0
    ? Math.round(((r.total_hoy - promAntes) / promAntes) * 100)
    : null
  const stockAlertas = alertasData?.total ?? 0

  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className={cn('grid gap-3', isMobile ? 'grid-cols-2' : 'grid-cols-2 lg:grid-cols-6')}>
        <KpiCard
          label="Ventas hoy"
          value={cop(r.total_hoy)}
          sub="Acumulado del día"
          icon="Wallet"
          pill={tendencia != null ? (tendencia >= 0 ? `▲ ${tendencia}% vs prom.` : `▼ ${Math.abs(tendencia)}% vs prom.`) : 'Sin comparativa'}
          pillTone={tendencia != null ? (tendencia >= 0 ? 'success' : 'warning') : 'neutral'}
        />
        <KpiCard label="Pedidos hoy" value={r.pedidos_hoy ?? 0} sub="Transacciones" icon="Receipt"
          pill={r.pedidos_hoy > 0 ? `Ticket prom: ${cop(r.ticket_prom)}` : 'Sin ventas aún'} pillTone="accent" />
        <KpiCard label="Stock con alerta" value={stockAlertas || '—'}
          sub={stockAlertas > 0 ? 'Sin precio o agotados' : 'Sin alertas'}
          icon="AlertTriangle"
          pill={stockAlertas > 0 ? 'Ver inventario' : 'Todo en orden'}
          pillTone={stockAlertas > 0 ? 'warning' : 'success'} />
        <KpiCard label="Ticket promedio" value={cop(r.ticket_prom)} sub="Últimos 7 días" icon="Calculator" />
        <KpiCard label="Total semana" value={cop(r.total_semana)} sub="Últimos 7 días" icon="CalendarRange" />
        <KpiCard label="Total mes"    value={cop(r.total_mes)}    sub="Mes en curso"   icon="CalendarDays" />
      </div>

      {/* Gráfica */}
      <Card className="p-5">
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold">Evolución de ventas</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Total del período <span className="text-primary font-semibold tabular">{cop(totalChart)}</span>
            </p>
          </div>
          <div className="flex gap-1 bg-surface-2 p-1 rounded-md">
            <PeriodToggle active={periodo === 'semana'} onClick={() => setPeriodo('semana')}>7 días</PeriodToggle>
            <PeriodToggle active={periodo === 'mes'}    onClick={() => setPeriodo('mes')}>Mes</PeriodToggle>
          </div>
        </div>
        {chartData.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">Sin datos para este período.</p>
        ) : (
          <ResponsiveContainer width="100%" height={isMobile ? 180 : 220}>
            <AreaChart data={chartData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gradArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="hsl(var(--accent))" stopOpacity={.25} />
                  <stop offset="95%" stopColor="hsl(var(--accent))" stopOpacity={0}   />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border-subtle))" vertical={false} />
              <XAxis dataKey="dia" tick={{ fill: 'hsl(var(--text-muted))', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: 'hsl(var(--text-muted))', fontSize: 9 }} axisLine={false} tickLine={false}
                tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
              />
              <Tooltip
                contentStyle={{
                  background: 'hsl(var(--bg-surface))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 8,
                  color: 'hsl(var(--text-primary))',
                  fontSize: 11,
                }}
                formatter={v => [cop(v), 'Ventas']}
                cursor={{ stroke: 'hsl(var(--accent))', strokeWidth: 1, strokeDasharray: '4 4' }}
              />
              <Area type="monotone" dataKey="ventas" stroke="hsl(var(--accent))" strokeWidth={2}
                fill="url(#gradArea)" dot={{ fill: 'hsl(var(--accent))', r: 2.5, strokeWidth: 0 }}
                activeDot={{ r: 4, fill: 'hsl(var(--accent))' }} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Métodos + Top 5 */}
      <div className={cn('grid gap-4', isMobile ? 'grid-cols-1' : 'grid-cols-2')}>
        <Card className="p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">Métodos de pago · Hoy</h2>
          {!ventasHoy ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : metodosData.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Sin ventas hoy.</p>
          ) : (
            <>
              <div className="flex items-center gap-4 mb-4">
                <ResponsiveContainer width={88} height={88}>
                  <PieChart>
                    <Pie data={metodosData} dataKey="value" cx="50%" cy="50%" innerRadius={26} outerRadius={42} paddingAngle={2} startAngle={90} endAngle={-270}>
                      {metodosData.map((_, i) => <Cell key={i} fill={METODO_COLORS[i % METODO_COLORS.length]} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div>
                  <div className="text-2xl font-semibold tracking-tight tabular">{cop(totalMetodos)}</div>
                  <div className="text-xs text-muted-foreground">
                    {metodosData.length} método{metodosData.length > 1 ? 's' : ''}
                  </div>
                </div>
              </div>
              <div>
                {metodosData.map((m, i) => (
                  <MetodoRow key={i} m={m} total={totalMetodos} color={METODO_COLORS[i % METODO_COLORS.length]} />
                ))}
              </div>
            </>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">Top 5 productos · Semana</h2>
          {!top5 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : top5.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Sin ventas esta semana.</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3 px-3 py-2 bg-surface-2 rounded-md">
                <span className="text-xs text-muted-foreground">Ingresos top 5</span>
                <span className="text-sm font-semibold text-primary tabular">
                  {cop(top5.reduce((a, p) => a + (p.ingresos || 0), 0))}
                </span>
              </div>
              <div>
                {top5.map((p, i) => <TopProductoRow key={i} p={p} i={i} max={maxTop5Ing} />)}
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Vendedores */}
      {vendedoresData.length > 0 && (
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Vendedores · Hoy</h2>
            <span className="text-xs text-muted-foreground">
              {vendedoresData.length} vendedor{vendedoresData.length > 1 ? 'es' : ''}
            </span>
          </div>
          <div>
            {vendedoresData.map((v, i) => <VendedorRow key={i} v={v} i={i} maxTotal={maxVendedor} />)}
          </div>
        </Card>
      )}
    </div>
  )
}

function PeriodToggle({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-3 py-1 text-xs rounded transition-colors',
        active
          ? 'bg-surface text-foreground shadow-xs font-medium'
          : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}
